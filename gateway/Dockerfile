# ---- Builder Stage ----
FROM rust:1-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a new empty shell project
WORKDIR /usr/src/app
COPY . .

# Build for release
RUN cargo build --release

# ---- Final Stage ----
FROM debian:stable-slim

# Copy the binary from the builder stage
COPY --from=builder /usr/src/app/target/release/gateway /usr/local/bin/gateway

# Expose port 8080
EXPOSE 8080

# Set the binary as the entrypoint
CMD ["/usr/local/bin/gateway"]
