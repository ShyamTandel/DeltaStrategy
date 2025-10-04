# DeltaStrategy

# DeltaStrategy - Delta Exchange API Integration

A Django REST API application that integrates with Delta Exchange to provide account data and market information.

## Features

- **Account Data API**: Fetch user profile, wallet balances, positions, orders, and trading preferences
- **Market Data API**: Get market data including products, tickers, orderbook, and trades (no authentication required)
- **Delta Authentication**: Secure HMAC-SHA256 signature-based authentication
- **Class-based API Views**: Clean, maintainable Django REST Framework implementation

## Setup Instructions

### 1. Clone and Install Dependencies

```bash
cd DeltaStrategy
pip install -r requirements.txt
```

### 2. Configure Environment Variables

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Get your Delta Exchange API credentials:
   - Visit: https://www.delta.exchange/app/account/manageapikeys
   - Create a new API key with appropriate permissions
   - Copy the API Key and Secret

3. Update the `.env` file with your credentials:
```env
API_KEY=your_delta_api_key_here
API_SECRET=your_delta_api_secret_here
```

### 3. Run the Application

```bash
python manage.py migrate
python manage.py runserver
```

The API will be available at: http://127.0.0.1:8000/

## API Endpoints

### 1. Health Check
- **URL**: `/api/health/`
- **Method**: GET
- **Authentication**: Not required
- **Description**: Simple health check endpoint

### 2. Account Data
- **URL**: `/api/delta/account/`
- **Methods**: GET, POST
- **Authentication**: Required (API_KEY and API_SECRET)
- **Description**: Get Delta Exchange account data

#### GET Request
Returns basic profile and wallet data:
```bash
curl http://127.0.0.1:8000/api/delta/account/
```

#### POST Request
Get specific data types:
```bash
curl -X POST http://127.0.0.1:8000/api/delta/account/ \
     -H "Content-Type: application/json" \
     -d '{"data_type": "wallet"}'
```

Available data types: `profile`, `wallet`, `positions`, `orders`, `preferences`, `all`

### 3. Market Data
- **URL**: `/api/delta/market/`
- **Method**: GET
- **Authentication**: Not required
- **Description**: Get public market data

#### Examples:
```bash
# Get all products
curl "http://127.0.0.1:8000/api/delta/market/?type=products"

# Get ticker for BTCUSD
curl "http://127.0.0.1:8000/api/delta/market/?type=ticker&symbol=BTCUSD"

# Get orderbook for BTCUSD
curl "http://127.0.0.1:8000/api/delta/market/?type=orderbook&symbol=BTCUSD"

# Get recent trades for BTCUSD
curl "http://127.0.0.1:8000/api/delta/market/?type=trades&symbol=BTCUSD"
```

### 4. API Documentation
- **URL**: `/api/docs/`
- **Method**: GET
- **Authentication**: Not required
- **Description**: Interactive API documentation

## Project Structure

```
DeltaStrategy/
├── api/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── serializers.py
│   ├── tests.py
│   └── views.py          # Main API implementation
├── deltastrategy/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py       # Django settings with env vars
│   ├── urls.py           # URL routing
│   └── wsgi.py
├── templates/
│   ├── base.html
│   └── home.html
├── .env.example          # Environment variables template
├── db.sqlite3
├── manage.py
├── requirements.txt
└── README.md
```

## Implementation Details

### Delta API Authentication
The application implements Delta Exchange's authentication mechanism using HMAC-SHA256 signatures:

1. **Signature Generation**: 
   ```python
   signature_data = method + timestamp + path + query_string + payload
   signature = HMAC-SHA256(api_secret, signature_data)
   ```

2. **Required Headers**:
   - `api-key`: Your Delta API key
   - `timestamp`: Current Unix timestamp
   - `signature`: HMAC signature
   - `User-Agent`: Client identifier
   - `Content-Type`: application/json

### Error Handling
- Comprehensive error handling for API requests
- Proper HTTP status codes
- Detailed error messages in responses

### Security Features
- Environment-based configuration
- Secure credential handling
- Request timeout protection
- Input validation

## Testing

Test the API endpoints using the provided examples or tools like Postman, curl, or the Django REST Framework browsable API.

### Example Response Format
```json
{
    "success": true,
    "data": {
        "profile": {
            "id": "user_id",
            "email": "user@example.com",
            "account_name": "Main",
            // ... more profile data
        },
        "wallet": {
            "balances": [
                {
                    "asset_symbol": "USD",
                    "balance": "1000.00",
                    "available_balance": "950.00"
                    // ... more balance data
                }
            ]
        }
    },
    "timestamp": "2024-01-01T12:00:00Z"
}
```

## Requirements

- Python 3.8+
- Django 5.2.7
- Django REST Framework 3.16.1
- requests 2.32.5
- python-dotenv 1.1.1

## Support

For Delta Exchange API documentation, visit: https://docs.delta.exchange/

For issues with this implementation, check the API responses and ensure your Delta API credentials are valid and have the necessary permissions.

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