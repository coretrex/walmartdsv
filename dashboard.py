import requests
import pandas as pd
import streamlit as st
import datetime
import uuid
import base64
import sqlite3
import time

# Ensure required modules are installed
try:
    import requests
    import pandas as pd
    import streamlit as st
except ModuleNotFoundError as e:
    st.error(f"Missing module: {e.name}. Please install the required dependencies.")
    raise

# Set page config to wide mode
st.set_page_config(
    page_title="Walmart DSV Dashboard",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Walmart DSV API Credentials
# Try to get credentials from environment variables first, fall back to hardcoded values
import os

CLIENT_ID = os.getenv("WALMART_CLIENT_ID", "f657e76c-6e19-4459-8fda-ecf3ee17db44")
CLIENT_SECRET = os.getenv("WALMART_CLIENT_SECRET", "ALsE88YTxPZ4dd7XKcF00FNKDlfjh9iIig7M5Z4AUabxn_KcJ6uKFcGtAdvfke5fgiDUqbXfXITzMg5U_ieEnKc")

# Walmart API endpoints - try both production and sandbox
TOKEN_URL = "https://marketplace.walmartapis.com/v3/token"
ORDERS_URL = "https://marketplace.walmartapis.com/v3/orders"
DEFAULT_SHIP_NODE = "39931104"

# Alternative endpoints for troubleshooting
SANDBOX_TOKEN_URL = "https://sandbox.walmartapis.com/v3/token"
SANDBOX_ORDERS_URL = "https://sandbox.walmartapis.com/v3/orders"

# Validate credentials format
if not CLIENT_ID or not CLIENT_SECRET:
    st.error("Missing Walmart API credentials. Please set WALMART_CLIENT_ID and WALMART_CLIENT_SECRET environment variables.")
    st.stop()

# Function to validate credentials format
def validate_credentials():
    """Validate that credentials are in the correct format"""
    if not CLIENT_ID or len(CLIENT_ID) < 10:
        st.error("Invalid CLIENT_ID format")
        return False
    if not CLIENT_SECRET or len(CLIENT_SECRET) < 10:
        st.error("Invalid CLIENT_SECRET format")
        return False
    
    # Test the base64 encoding
    try:
        credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        st.write(f"Credentials encoded successfully. Length: {len(encoded_credentials)}")
        return True
    except Exception as e:
        st.error(f"Error encoding credentials: {e}")
        return False

# Function to test different API endpoints
def test_api_endpoints():
    """Test both production and sandbox endpoints"""
    endpoints = [
        ("Production", TOKEN_URL),
        ("Sandbox", SANDBOX_TOKEN_URL)
    ]
    
    results = []
    for name, url in endpoints:
        try:
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
            
            response = requests.post(url, headers=headers, data=data, timeout=10)
            results.append((name, url, response.status_code, response.text))
        except Exception as e:
            results.append((name, url, "ERROR", str(e)))
    
    return results

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
        
        # Debug information
        st.write(f"Token request status: {response.status_code}")
        st.write(f"Token request headers: {dict(headers)}")
        
        if response.status_code != 200:
            st.error(f"Token request failed with status {response.status_code}")
            st.error(f"Response text: {response.text}")
            return None
            
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            st.error(f"Error: No access token received. Full response: {token_data}")
            return None
        return access_token
    except requests.RequestException as e:
        st.error(f"Failed to get Walmart API token: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            st.error(f"Response status: {e.response.status_code}")
            st.error(f"Response text: {e.response.text}")
        return None

# Function to fetch latest order from Walmart API
def fetch_latest_order(token, start_date, end_date):
    if not token:
        st.error("Error: No valid token provided for fetching orders.")
        return []
    
    # Validate dates
    today = datetime.date.today()
    if start_date > today or end_date > today:
        st.error("Cannot fetch orders for future dates.")
        return []
    
    if (end_date - start_date).days > 180:
        st.error("Please select a date range of 180 days or less.")
        return []
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "WM_SVC.NAME": "Walmart Marketplace",
        "WM_SEC.ACCESS_TOKEN": token
    }
    params = {
        "shipNode": DEFAULT_SHIP_NODE,
        "limit": 100,
        "createdStartDate": start_date.strftime('%Y-%m-%dT00:00:00.000Z'),
        "createdEndDate": end_date.strftime('%Y-%m-%dT23:59:59.999Z')
    }
    
    all_orders = []
    progress_bar = st.progress(0)
    page_count = 0
    max_pages = 5
    
    try:
        while page_count < max_pages:
            page_count += 1
            
            try:
                response = requests.get(ORDERS_URL, headers=headers, params=params)
                
                if response.status_code == 429:
                    time.sleep(1)
                    continue
                    
                response.raise_for_status()
                orders = response.json()
                
            except Exception as e:
                st.error(f"Error fetching orders: {str(e)}")
                break
            
            order_list = orders.get("list", {}).get("elements", {}).get("order", [])
            if not order_list:
                break
            
            all_orders.extend(order_list)
            progress_bar.progress(page_count / max_pages)
            
            next_cursor = orders.get("list", {}).get("meta", {}).get("nextCursor")
            if not next_cursor:
                break
                
            params["nextCursor"] = next_cursor
            time.sleep(0.2)

        progress_bar.empty()
        
        # Remove any duplicates based on purchaseOrderId
        unique_orders = {order.get("purchaseOrderId"): order for order in all_orders if isinstance(order, dict)}.values()
        final_orders = list(unique_orders)
        
        if final_orders:
            st.success(f"Successfully fetched {len(final_orders)} orders")
            
        return sorted(final_orders, key=lambda x: x.get("orderDate", ""), reverse=True)

    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return []

# Add these functions after the existing imports and before the page config

def init_database():
    """Initialize SQLite database and create tables if they don't exist"""
    conn = sqlite3.connect('walmart_orders.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            purchase_order_id TEXT PRIMARY KEY,
            sku TEXT,
            item_name TEXT,
            quantity REAL,
            unit_price REAL,
            order_date TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_orders_to_db(processed_orders):
    """Save orders to SQLite database, skipping duplicates"""
    conn = sqlite3.connect('walmart_orders.db')
    c = conn.cursor()
    
    for order in processed_orders:
        try:
            c.execute('''
                INSERT OR IGNORE INTO orders 
                (purchase_order_id, sku, item_name, quantity, unit_price, order_date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                order['Purchase Order ID'],
                order['SKU'],
                order['Item Name'],
                order['Quantity'],
                order['Unit Price ($)'],
                order['Order Date']
            ))
        except sqlite3.Error as e:
            st.error(f"Database error: {e}")
    
    conn.commit()
    conn.close()

# Streamlit Dashboard Setup
st.title("Walmart DSV Dashboard")

# Add troubleshooting information
with st.expander("🔍 Troubleshooting Authentication Issues"):
    st.markdown("""
    **Common causes of UNAUTHORIZED errors:**
    
    1. **Expired Credentials**: Your Client ID or Client Secret may have expired
    2. **Wrong Environment**: You might be using production credentials with sandbox endpoints or vice versa
    3. **Incorrect Format**: The credentials might not be in the correct format
    4. **API Access**: Your account might not have access to the specific API endpoints
    5. **Rate Limiting**: You might be hitting rate limits
    
    **Steps to resolve:**
    
    1. **Check your Walmart Developer Portal**: Verify your credentials are still active
    2. **Use Environment Variables**: Set your credentials as environment variables for security:
       ```bash
       export WALMART_CLIENT_ID="your_client_id"
       export WALMART_CLIENT_SECRET="your_client_secret"
       ```
    3. **Test with the debug tools**: Use the debug section in the sidebar to test your credentials
    4. **Contact Walmart Support**: If the issue persists, contact Walmart Developer Support
    
    **Current Status**: Use the debug tools in the sidebar to test your authentication.
    """)

# Add custom CSS to make the table larger and reduce margins/padding
st.markdown("""
    <style>
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
            max-width: 98%;
        }
        .stDataFrame {
            width: 100%;
        }
        .stDataFrame [data-testid="stDataFrameResizable"] {
            min-height: 450px;
            width: 100%;
        }
        section[data-testid="stSidebar"] {
            width: 350px !important;
            padding: 2rem 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# Sidebar controls
with st.sidebar:
    st.header("Settings")
    
    # Add debug section
    with st.expander("🔧 Debug Authentication"):
        st.write("**Current Credentials:**")
        st.write(f"Client ID: {CLIENT_ID[:8]}...{CLIENT_ID[-8:] if len(CLIENT_ID) > 16 else CLIENT_ID}")
        st.write(f"Client Secret: {CLIENT_SECRET[:8]}...{CLIENT_SECRET[-8:] if len(CLIENT_SECRET) > 16 else CLIENT_SECRET}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Test Credentials"):
                if validate_credentials():
                    st.success("Credentials format is valid")
                    token = get_walmart_token()
                    if token:
                        st.success("✅ Authentication successful!")
                        st.write(f"Token: {token[:20]}...{token[-20:] if len(token) > 40 else token}")
                    else:
                        st.error("❌ Authentication failed")
                else:
                    st.error("❌ Credentials format is invalid")
        
        with col2:
            if st.button("Test Endpoints"):
                st.write("Testing API endpoints...")
                results = test_api_endpoints()
                for name, url, status, response in results:
                    st.write(f"**{name}:** {url}")
                    st.write(f"Status: {status}")
                    if status == 200:
                        st.success("✅ Endpoint working")
                    else:
                        st.error(f"❌ Error: {response[:200]}...")
                    st.write("---")
    
    # Add SKU filter
    if 'latest_order' in st.session_state and st.session_state['latest_order']:
        all_skus = sorted(list(set(
            item.get("item", {}).get("sku", "N/A") 
            for order in st.session_state['latest_order'] 
            for item in order.get("orderLines", {}).get("orderLine", [])
            if isinstance(item, dict)
        )))
        selected_sku = st.selectbox("Filter by SKU", ["All"] + all_skus)
    else:
        selected_sku = "All"
    
    # Modify date range selector with validation
    today = datetime.date.today()
    default_start = today - datetime.timedelta(days=7)
    selected_date_range = st.date_input(
        "Select Date Range",
        value=(default_start, today),
        max_value=today,  # Prevent selecting future dates
        help="Select a date range up to 180 days"
    )
    
    refresh = st.button("Refresh Data")

# Update the data fetching logic with validation
if refresh or 'latest_order' not in st.session_state:
    if len(selected_date_range) == 2:
        start_date, end_date = selected_date_range
        if start_date <= end_date and end_date <= today:
            token = get_walmart_token()
            if token:
                with st.spinner('Fetching orders...'):  # Add loading indicator
                    latest_order = fetch_latest_order(token, start_date, end_date)
                    st.session_state['latest_order'] = latest_order
        else:
            st.error("Invalid date range selected. End date must not be in the future.")

# Process Latest Order Data
processed_order = []
if 'latest_order' in st.session_state:
    latest_order = st.session_state['latest_order']
    if latest_order:
        # Initialize database
        init_database()
        
        # Process orders as before
        for order in latest_order:
            if isinstance(order, dict):
                order_lines = order.get("orderLines", {}).get("orderLine", [])
                
                # Process each order line
                for line in order_lines:
                    if isinstance(line, dict):
                        item = line.get("item", {})
                        
                        # Get amount from the specific path in charges
                        charges = line.get("charges", {})
                        charge_list = charges.get("charge", [])
                        unit_price = 0
                        if charge_list and isinstance(charge_list, list):
                            first_charge = charge_list[0]
                            if isinstance(first_charge, dict):
                                charge_amount = first_charge.get("chargeAmount", {})
                                unit_price = float(charge_amount.get("amount", 0))
                        
                        quantity = float(line.get("orderLineQuantity", {}).get("amount", 1))
                        quantity = quantity if quantity > 0 else 1
                        
                        processed_order.append({
                            "SKU": item.get("sku", "N/A"),
                            "Item Name": item.get("productName", "N/A"),
                            "Quantity": quantity,
                            "Unit Price ($)": unit_price,
                            "Purchase Order ID": order.get("purchaseOrderId", "N/A"),
                            "Order Date": datetime.datetime.fromtimestamp(
                                int(str(order.get("orderDate", 0))[:10])
                            ).strftime('%Y-%m-%d %H:%M:%S')
                        })
        
        # After creating processed_order list, save to database
        save_orders_to_db(processed_order)
        
        # Create DataFrame from database instead of processed_order
        conn = sqlite3.connect('walmart_orders.db')
        df = pd.read_sql_query('''
            SELECT 
                sku as "SKU",
                item_name as "Item Name",
                quantity as "Quantity",
                unit_price as "Unit Price ($)",
                purchase_order_id as "Purchase Order ID",
                order_date as "Order Date"
            FROM orders
        ''', conn)
        conn.close()
        
        # Convert orderDate to datetime
        if "Order Date" in df.columns:
            df["Order Date"] = pd.to_datetime(df["Order Date"])
        
        # Format numeric columns
        if "Unit Price ($)" in df.columns:
            df["Unit Price ($)"] = df["Unit Price ($)"].round(2)
        
        # Apply filters
        if selected_sku != "All":
            df = df[df["SKU"] == selected_sku]
            
        if len(selected_date_range) == 2:
            start_date, end_date = selected_date_range
            df = df[
                (df["Order Date"].dt.date >= start_date) & 
                (df["Order Date"].dt.date <= end_date)
            ]
        
        # Display Data
        if not df.empty:
            # Style the dataframe
            st.dataframe(
                df,
                hide_index=True,
                height=450,
                use_container_width=True,
                column_config={
                    "SKU": st.column_config.TextColumn(
                        "SKU",
                        width=120  # Increased width for SKU column
                    ),
                    "Item Name": st.column_config.TextColumn(
                        "Item Name",
                        width="large"
                    ),
                    "Quantity": st.column_config.NumberColumn(
                        "Quantity",
                        width="small",
                        format="%d"
                    ),
                    "Unit Price ($)": st.column_config.NumberColumn(
                        "Unit Price ($)",
                        width="small",
                        format="$%.2f"
                    ),
                    "Purchase Order ID": st.column_config.TextColumn(
                        "Purchase Order ID",
                        width="medium",
                        help="Walmart Purchase Order ID"
                    ),
                    "Order Date": st.column_config.DatetimeColumn(
                        "Order Date",
                        width="medium",
                        format="MM/DD/YYYY HH:mm"
                    )
                }
            )
            
            # Display order summary in metrics
            st.header("Order Summary")
            col1, col2 = st.columns(2)
            with col1:
                total_amount = (df["Quantity"] * df["Unit Price ($)"]).sum()
                st.metric("Total Order Amount", f"${total_amount:,.2f}")
            with col2:
                st.metric("Total Items", f"{df['Quantity'].sum():.0f}")
        else:
            st.warning("No orders found for the selected criteria.")
