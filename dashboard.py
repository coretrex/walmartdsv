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
    
    if (end_date - start_date).days > 180:  # Optional: Add a reasonable date range limit
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
    try:
        while True:
            response = requests.get(ORDERS_URL, headers=headers, params=params)
            if response.status_code == 404:
                break  # No more orders to fetch
            response.raise_for_status()
            orders = response.json()
            
            if not orders:
                break
                
            order_list = orders.get("list", {}).get("elements", {}).get("order", [])
            
            if not order_list:
                break
            
            order_list = [o for o in order_list if isinstance(o, dict)]
            all_orders.extend(order_list)
            
            # Check if there are more pages
            next_cursor = orders.get("list", {}).get("meta", {}).get("nextCursor")
            if not next_cursor:
                break
                
            # Update params for next page
            params["nextCursor"] = next_cursor

        return sorted(all_orders, key=lambda x: x.get("orderDate", ""), reverse=True)

    except requests.RequestException as e:
        st.error(f"Failed to fetch orders from Walmart API: {str(e)}")
        if hasattr(e.response, 'text'):
            st.error(f"API Response: {e.response.text}")
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
