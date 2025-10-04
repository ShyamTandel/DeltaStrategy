# DeltaStrategy

A Django REST API application for managing trading strategies, trades, and portfolios.

## Quick Start

1. **Activate virtual environment:**
   ```bash
   venv\Scripts\activate
   ```

2. **Start the development server:**
   ```bash
   python manage.py runserver
   ```

3. **Access the API:**
   - API Base URL: http://localhost:8000/api/
   - Admin Interface: http://localhost:8000/admin/
   - Health Check: http://localhost:8000/api/health/

## API Endpoints

- **Health Check:** `GET /api/health/`
- **Strategies:** `GET|POST /api/strategies/`
- **Strategy Detail:** `GET|PUT|DELETE /api/strategies/{id}/`
- **Trades:** `GET|POST /api/trades/`
- **Trade Detail:** `GET|PUT|DELETE /api/trades/{id}/`
- **Portfolios:** `GET /api/portfolios/`

## Documentation

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for complete API documentation.

## Technology Stack

- Django 5.2.7
- Django REST Framework 3.16.1
- Django CORS Headers 4.9.0
- SQLite Database (development)