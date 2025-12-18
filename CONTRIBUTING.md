# Contributing to Automatyczny Stock Market

Thank you for your interest in contributing to this automated trading system! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Set up the development environment following the README instructions
4. Create a feature branch for your changes

## Development Environment Setup

### Prerequisites
- Python 3.8+
- SQLite (3.x, wbudowany)

### Local Development
```bash
# Clone the repository
git clone https://github.com/filipsliwa/Automatyczny-Stock-Market.git
cd "Automatyczny Stock Market"

# Install Python dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration

# Initialize database
database/init_database.py  # uruchamia skrypt inicjalizujący SQLite
python init_database.py

# Run the FastAPI application
python fastapi_app.py
```

## Project Structure

```
├── fastapi_app.py         # Main FastAPI application
├── bot/                   # Trading bot modules
│   ├── config.py         # Configuration management
│   ├── db.py             # Database models (SQLAlchemy)
│   ├── auto_trader.py    # Trading logic
│   └── exchanges/        # Exchange integrations (CCXT)
├── templates/            # Jinja2 HTML templates
├── static/               # Static files (CSS, JS)
├── user_database.py      # User management
├── trading.db            # SQLite database
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables
└── logs/                 # Application logs
```

## Coding Standards

### Python Code
- Follow PEP 8 style guidelines
- Use type hints where possible
- Write docstrings for functions and classes
- Maximum line length: 88 characters (Black formatter)

### JavaScript/Node.js Code
- Not applicable for this project (Python-only)

### Trading Algorithms
- Include comprehensive backtesting
- Document strategy logic clearly
- Implement proper risk management
- Add performance metrics

## Testing

### Running Tests
```bash
# Python tests
pytest tests/

# Integration tests
python -m pytest tests/integration/

# Test FastAPI endpoints
python -c "import requests; print(requests.get('http://localhost:8000/').status_code)"
```

### Test Coverage
- Aim for 80%+ test coverage
- Include unit tests for all new functions
- Add integration tests for API endpoints
- Test trading strategies with historical data

## Trading Strategy Development

### Strategy Requirements
1. **Backtesting**: Every strategy must include historical backtesting
2. **Risk Management**: Implement stop-loss and position sizing
3. **Documentation**: Clear explanation of strategy logic
4. **Performance Metrics**: Include Sharpe ratio, max drawdown, etc.

### Strategy Template
```python
class TradingStrategy:
    def __init__(self, config):
        self.config = config
        
    def analyze(self, market_data):
        """Analyze market data and generate signals"""
        pass
        
    def execute(self, signal):
        """Execute trading decision"""
        pass
        
    def backtest(self, historical_data):
        """Backtest strategy performance"""
        pass
```

## Pull Request Process

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Write clean, documented code
   - Add tests for new functionality
   - Update documentation as needed

3. **Test Changes**
   ```bash
   pytest tests/
   python fastapi_app.py  # Test local server
   ```

4. **Commit Changes**
   ```bash
   git commit -m "feat: add new trading strategy"
   ```

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Commit Message Convention

Use conventional commits format:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance tasks

Examples:
```
feat: add RSI-based trading strategy
fix: resolve authentication timeout issue
docs: update API documentation
```

## Security Guidelines

### API Security
- Never commit API keys or secrets
- Use environment variables for sensitive data
- Implement proper authentication and authorization
- Validate all user inputs

### Trading Security
- Implement position limits
- Add circuit breakers for losses
- Log all trading activities
- Use secure exchange connections

## Performance Guidelines

### Database Operations
- Use connection pooling
- Implement proper indexing
- Avoid N+1 queries
- Use async operations where possible

### Trading Performance
- Minimize API calls to exchanges
- Implement rate limiting
- Use WebSocket connections for real-time data
- Cache frequently accessed data

## Documentation

### Code Documentation
- Write clear docstrings
- Include examples in documentation
- Document configuration options
- Maintain API documentation

### User Documentation
- Update README for new features
- Include setup instructions
- Provide troubleshooting guides
- Document deployment procedures

## Issue Reporting

### Bug Reports
Use the bug report template and include:
- Steps to reproduce
- Expected vs actual behavior
- Environment details
- Log outputs

### Feature Requests
Use the feature request template and include:
- Problem description
- Proposed solution
- Use cases
- Implementation considerations

### Trading Strategy Requests
Use the trading strategy template and include:
- Strategy description
- Technical indicators needed
- Risk management approach
- Backtesting requirements

## Community Guidelines

### Code of Conduct
- Be respectful and inclusive
- Provide constructive feedback
- Help newcomers learn
- Focus on collaboration

### Communication
- Use clear, descriptive titles
- Provide context in discussions
- Reference related issues/PRs
- Follow up on conversations

## Getting Help

- **Documentation**: Check the README and wiki
- **Issues**: Search existing issues first
- **Discussions**: Use GitHub Discussions for questions
- **Discord**: Join our community Discord server

## Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation
- Community highlights

Thank you for contributing to the Automatyczny Stock Market project!
