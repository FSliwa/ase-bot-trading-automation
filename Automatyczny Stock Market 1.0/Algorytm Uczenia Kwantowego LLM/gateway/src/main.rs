use anyhow::Result;
use axum::{
    body::Bytes,
    extract::{DefaultBodyLimit, Json, State},
    http::{HeaderMap, Method, StatusCode, Uri},
    response::IntoResponse,
    routing::{any, get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::{env, net::SocketAddr, sync::Arc};
use tower_http::{
    cors::CorsLayer,
    trace::TraceLayer,
};
use hyper::header::{self, HeaderName, HeaderValue};

#[derive(Clone)]
struct AppState {
    backend_base: String,
    client: reqwest::Client,
}

#[derive(Deserialize, Serialize)]
struct LoginPayload {
    email: String,
    password: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    let backend_base = env::var("BACKEND_BASE").unwrap_or_else(|_| "http://127.0.0.1:8009".to_string());
    let listen_addr: SocketAddr = env::var("GATEWAY_ADDR")
        .unwrap_or_else(|_| "0.0.0.0:8080".into())
        .parse()
        .expect("invalid GATEWAY_ADDR");

    let state = Arc::new(AppState {
        backend_base,
        client: reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(std::time::Duration::from_secs(15))
            .pool_idle_timeout(Some(std::time::Duration::from_secs(10)))
            .build()?,
    });

    let cors = CorsLayer::new()
        .allow_origin("https://ase-bot.live".parse::<HeaderValue>()?)
        .allow_origin("https://www.ase-bot.live".parse::<HeaderValue>()?)
        .allow_methods(vec![
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers(vec![
            header::ACCEPT,
            header::AUTHORIZATION,
            header::CONTENT_TYPE,
            HeaderName::from_static("x-csrf-token"),
        ])
        .allow_credentials(false);

    let app = Router::new()
        .route("/health", get(health))
        .route("/api/login", post(api_login))
        .route("/api/analysis/market", post(api_analysis_market))
        .route("/", get(proxy_root_get)) // Explicitly handle root GET
        .route("/*path", any(proxy_all)) // Fallback route
        .layer(cors) // Apply the configured CORS layer
        .layer(DefaultBodyLimit::max(10 * 1024 * 1024))
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    tracing::info!("listening on {}", listen_addr);
    let listener = tokio::net::TcpListener::bind(listen_addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

async fn health() -> impl IntoResponse {
    (StatusCode::OK, "{\"status\":\"ok\"}")
}

async fn api_login(State(state): State<Arc<AppState>>, Json(payload): Json<LoginPayload>) -> impl IntoResponse {
    let url = format!("{}/api/login", state.backend_base);
    let res = state.client.post(url).json(&payload).send().await;
    match res {
        Ok(r) => {
            let status = StatusCode::from_u16(r.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            let content_type_header = r.headers().get(reqwest::header::CONTENT_TYPE).cloned();
            let body = r.bytes().await.unwrap_or_else(|_| Bytes::from_static(b"{}"));
            let mut response = (status, body).into_response();
            if let Some(ct) = content_type_header {
                response.headers_mut().insert(axum::http::header::CONTENT_TYPE, ct);
            }
            response
        }
        Err(e) => {
            let body = format!("{{\"error\":\"backend_error\",\"message\":{:?}}}", e);
            (StatusCode::BAD_GATEWAY, body).into_response()
        }
    }
}

async fn api_analysis_market(State(state): State<Arc<AppState>>, headers: HeaderMap, body: axum::body::Bytes) -> impl IntoResponse {
    let url = format!("{}/api/analysis/market", state.backend_base);
    let mut req = state.client.post(url);
    if let Some(ct) = headers.get("content-type") {
        req = req.header("content-type", ct);
    }
    let res = req.body(body).send().await;
    match res {
        Ok(r) => {
            let status = StatusCode::from_u16(r.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            let content_type_header = r.headers().get(reqwest::header::CONTENT_TYPE).cloned();
            let body = r.bytes().await.unwrap_or_else(|_| Bytes::from_static(b"{}"));
            let mut response = (status, body).into_response();
            if let Some(ct) = content_type_header {
                response.headers_mut().insert(axum::http::header::CONTENT_TYPE, ct);
            }
            response
        }
        Err(e) => {
            let body = format!("{{\"error\":\"backend_error\",\"message\":{:?}}}", e);
            (StatusCode::BAD_GATEWAY, body).into_response()
        }
    }
}

async fn proxy_all(
    State(state): State<Arc<AppState>>,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
    body: Bytes,
) -> impl IntoResponse {
    let mut url = format!("{}{}", state.backend_base, uri.path());
    if let Some(q) = uri.query() { url.push('?'); url.push_str(q); }

    let rb = match method {
        Method::GET => state.client.get(&url),
        Method::POST => state.client.post(&url),
        Method::PUT => state.client.put(&url),
        Method::PATCH => state.client.patch(&url),
        Method::DELETE => state.client.delete(&url),
        _ => state.client.request(method.clone(), &url),
    };

    // Ensure critical headers like Authorization are always passed through
    let mut req = rb;
    if let Some(auth_header) = headers.get("authorization") {
        req = req.header("authorization", auth_header);
    }
    if let Some(ct) = headers.get("content-type") {
        req = req.header("content-type", ct);
    }
    if let Some(cookie) = headers.get("cookie") {
        req = req.header("cookie", cookie);
    }
    // Explicitly forward the CSRF token header
    if let Some(csrf_token) = headers.get("x-csrf-token") {
        req = req.header("x-csrf-token", csrf_token);
    }

    let res = if method == Method::GET || body.is_empty() {
        req.send().await
    } else {
        req.body(body).send().await
    };

    match res {
        Ok(r) => {
            let status = StatusCode::from_u16(r.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
            // First, clone headers we want to preserve before consuming the body
            let content_type_header = r.headers().get(reqwest::header::CONTENT_TYPE).cloned();
            let location_header = r.headers().get(reqwest::header::LOCATION).cloned();
            let set_cookie_values: Vec<axum::http::header::HeaderValue> = r
                .headers()
                .get_all(reqwest::header::SET_COOKIE)
                .iter()
                .cloned()
                .collect();

            let body = r.bytes().await.unwrap_or_else(|_| Bytes::from_static(b""));

            let mut response = (status, body).into_response();
            if let Some(ct) = content_type_header {
                response
                    .headers_mut()
                    .insert(axum::http::header::CONTENT_TYPE, ct);
            }
            if let Some(loc) = location_header {
                response
                    .headers_mut()
                    .insert(axum::http::header::LOCATION, loc);
            }
            for sc in set_cookie_values {
                response
                    .headers_mut()
                    .append(axum::http::header::SET_COOKIE, sc);
            }
            response
        }
        Err(e) => {
            let body = format!("{{\"error\":\"backend_error\",\"message\":\"{:?}\"}}", e);
            (StatusCode::BAD_GATEWAY, body).into_response()
        }
    }
}

// Explicit GET handler for the root path to ensure the login page loads.
async fn proxy_root_get(
    State(state): State<Arc<AppState>>,
    method: Method,
    uri: Uri,
    headers: HeaderMap,
) -> impl IntoResponse {
    // We can reuse the `proxy_all` logic by passing an empty body
    proxy_all(State(state), method, uri, headers, Bytes::new()).await
}


