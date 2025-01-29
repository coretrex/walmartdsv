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

# Function to fetch latest order from Walmart API
def fetch_latest_order(token):
    if not token:
        st.error("Error: No valid token provided for fetching orders.")
        return []
    
    st.info("Attempting to fetch orders...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "WM_SVC.NAME": "Walmart Marketplace",
        "WM_SEC.ACCESS_TOKEN": token
    }
    params = {
        "shipNode": DEFAULT_SHIP_NODE,
        "limit": 10,  # Increased to ensure we get enough orders
        "createdStartDate": (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%dT00:00:00.000Z')
    }
    try:
        response = requests.get(ORDERS_URL, headers=headers, params=params)
        response.raise_for_status()
        orders = response.json()
        
        # Debug logs
        st.info(f"API Response Status Code: {response.status_code}")
        
        if not orders:
            st.warning("Received empty response from API")
            return []
            
        # Get the order list from the correct path in the response
        order_list = orders.get("list", {}).get("elements", {}).get("order", [])
        
        if not order_list:
            st.warning("No orders found in the response")
            return []
        
        st.info(f"Found {len(order_list)} orders")
        
        # Sort by orderDate in descending order and take the last 5 orders
        order_list = [o for o in order_list if isinstance(o, dict)]
        if not order_list:
            st.warning("No valid orders found in the response")
            return []
        
        # Sort by orderDate in descending order and take the first 5
        sorted_orders = sorted(order_list, key=lambda x: x.get("orderDate", ""), reverse=True)[:5]
        return sorted_orders  # Return the 5 most recent orders
    except requests.RequestException as e:
        st.error(f"Failed to fetch latest order from Walmart API: {str(e)} - Response: {response.text}")
        return []

# Streamlit Dashboard Setup
st.title("Walmart DSV Latest Order Dashboard")

# Sidebar controls
st.sidebar.header("Settings")
refresh = st.sidebar.button("Refresh Data")

# Get the data
if refresh or 'latest_order' not in st.session_state:
    token = get_walmart_token()
    if token:
        latest_order = fetch_latest_order(token)
        st.session_state['latest_order'] = latest_order

# Process Latest Order Data
if 'latest_order' in st.session_state:
    latest_order = st.session_state['latest_order']
    if latest_order:
        processed_order = []
        for order in latest_order:
            if isinstance(order, dict):
                order_lines = order.get("orderLines", {}).get("orderLine", [])
                
                # Process each order line
                for line in order_lines:
                    if isinstance(line, dict):
                        item = line.get("item", {})
                        
                        # Debug the charges structure
                        charges = line.get("charges", [])
                        amount = 0
                        
                        try:
                            amount = float(line.get("amount", 0))
                        except (ValueError, TypeError):
                            if isinstance(charges, list) and charges:
                                try:
                                    first_charge = charges[0]
                                    if isinstance(first_charge, dict):
                                        charge_amount = first_charge.get("chargeAmount", {})
                                        amount = float(charge_amount.get("amount", 0))
                                except (IndexError, ValueError, TypeError):
                                    amount = 0
                        
                        quantity = float(line.get("orderLineQuantity", {}).get("amount", 1))
                        quantity = quantity if quantity > 0 else 1
                        
                        processed_order.append({
                            "SKU": item.get("sku", "N/A"),
                            "Item Name": item.get("productName", "N/A"),
                            "Quantity": quantity,
                            "Unit Price ($)": amount / quantity if quantity > 0 else 0,
                            "Total Line Amount ($)": amount,
                            "Purchase Order ID": order.get("purchaseOrderId", "N/A"),
                            "Order Date": order.get("orderDate", "N/A"),
                            "Status": order.get("orderStatus", "N/A")
                        })
        
        df = pd.DataFrame(processed_order)
        
        # Convert orderDate to datetime and format it
        if "Order Date" in df.columns:
            df["Order Date"] = pd.to_datetime(df["Order Date"]).dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Format numeric columns
        if "Unit Price ($)" in df.columns:
            df["Unit Price ($)"] = df["Unit Price ($)"].round(2)
        if "Total Line Amount ($)" in df.columns:
            df["Total Line Amount ($)"] = df["Total Line Amount ($)"].round(2)
        
        # Add SKU filter in sidebar
        st.sidebar.header("Filters")
        all_skus = ["All"] + sorted(df["SKU"].unique().tolist())
        selected_sku = st.sidebar.selectbox("Filter by SKU", all_skus)
        
        # Apply SKU filter
        if selected_sku != "All":
            df = df[df["SKU"] == selected_sku]
        
        # Display Data
        st.header("Order Details")
        if not df.empty:
            # Style the dataframe
            st.dataframe(
                df,
                hide_index=True,
                column_config={
                    "SKU": st.column_config.TextColumn(
                        "SKU",
                        width="small"
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
                    "Total Line Amount ($)": st.column_config.NumberColumn(
                        "Total Line Amount ($)",
                        width="medium",
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
                    ),
                    "Status": st.column_config.TextColumn(
                        "Status",
                        width="small"
                    )
                }
            )
            
            # Display order summary in metrics
            st.header("Order Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Order Amount", f"${df['Total Line Amount ($)'].sum():.2f}")
            with col2:
                st.metric("Total Items", f"{df['Quantity'].sum():.0f}")
            with col3:
                st.metric("Number of Orders", f"{df['Purchase Order ID'].nunique()}")
        else:
            st.warning("No orders found for the selected criteria.")
