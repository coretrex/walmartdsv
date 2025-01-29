import requests
import pandas as pd
import streamlit as st
import datetime
import uuid
import base64

# Ensure required modules are installed
try:
    import requests
    import pandas as pd
    import streamlit as st
except ModuleNotFoundError as e:
    st.error(f"Missing module: {e.name}. Please install the required dependencies.")
    raise

# Walmart DSV API Credentials
CLIENT_ID = "f657e76c-6e19-4459-8fda-ecf3ee17db44"
CLIENT_SECRET = "ALsE88YTxPZ4dd7XKcF00FNKDlfjh9iIig7M5Z4AUabxn_KcJ6uKFcGtAdvfke5fgiDUqbXfXITzMg5U_ieEnKc"
TOKEN_URL = "https://marketplace.walmartapis.com/v3/token"
ORDERS_URL = "https://marketplace.walmartapis.com/v3/orders"
DEFAULT_SHIP_NODE = "39931104"

# Function to get Walmart API token
def get_walmart_token():
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}",
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "WM_SVC.NAME": "Walmart Marketplace"
    }
    data = "grant_type=client_credentials"
    try:
        response = requests.post(TOKEN_URL, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            st.error(f"Error: No access token received. Full response: {token_data}")
            return None
        return access_token
    except requests.RequestException as e:
        st.error(f"Failed to get Walmart API token: {str(e)} - Response: {response.text}")
        return None

# Function to fetch orders from Walmart API
def fetch_orders(token):
    if not token:
        st.error("Error: No valid token provided for fetching orders.")
        return []
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "WM_SVC.NAME": "Walmart Marketplace",
        "WM_SEC.ACCESS_TOKEN": token
    }
    # Limit the date range to the last 3 days
    start_date = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime('%Y-%m-%dT00:00:00.000Z')
    end_date = datetime.datetime.now().strftime('%Y-%m-%dT23:59:59.000Z')
    params = {
        "shipNode": DEFAULT_SHIP_NODE,
        "createdStartDate": start_date,
        "createdEndDate": end_date
    }
    try:
        response = requests.get(ORDERS_URL, headers=headers, params=params)
        response.raise_for_status()
        orders = response.json()
        st.subheader("API Response")
        st.json(orders)  # Display full API response for debugging
        return orders.get("list", {}).get("elements", [])  # Adjusted based on API response structure
    except requests.RequestException as e:
        st.error(f"Failed to fetch orders from Walmart API: {str(e)} - Response: {response.text}")
        return []

# Streamlit Dashboard Setup
st.title("Walmart DSV Sales Dashboard")
st.sidebar.header("Settings")
refresh = st.sidebar.button("Refresh Data")

if refresh or 'orders' not in st.session_state:
    token = get_walmart_token()
    if token:
        orders = fetch_orders(token)
        st.session_state['orders'] = orders

# Process Orders Data
if 'orders' in st.session_state:
    orders = st.session_state['orders']
    if orders:
        df = pd.DataFrame(orders)
        if "purchaseOrderId" not in df.columns:
            st.error("Expected 'purchaseOrderId' column not found in API response.")
        else:
            if "orderDate" in df.columns:
                df["orderDate"] = pd.to_datetime(df["orderDate"], errors='coerce')
            
            if "orderLines" in df.columns:
                df["totalAmount"] = df["orderLines"].apply(lambda x: sum(line.get("charges", [{}])[0].get("chargeAmount", 0) for line in x) if isinstance(x, list) else 0)
            
            # Display Data
            st.subheader("Sales Overview")
            total_sales = df["totalAmount"].sum()
            total_orders = len(df)
            st.metric("Total Sales", f"${total_sales:,.2f}")
            st.metric("Total Orders", total_orders)
            
            # Sales Over Time
            if "orderDate" in df.columns:
                df['date'] = df['orderDate'].dt.date
                sales_summary = df.groupby('date')["totalAmount"].sum().reset_index()
                st.line_chart(sales_summary.set_index('date'))
            
            # Formatted Data Table
            st.subheader("Order Details")
            st.dataframe(df[["purchaseOrderId", "orderDate", "totalAmount"]])
    else:
        st.warning("No orders found.")
