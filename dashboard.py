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
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "WM_QOS.CORRELATION_ID": str(uuid.uuid4()),
        "WM_SVC.NAME": "Walmart Marketplace",
        "WM_SEC.ACCESS_TOKEN": token
    }
    params = {
        "shipNode": DEFAULT_SHIP_NODE,
        "limit": 5,  # Retrieve last 5 orders to sort and get latest
        "createdStartDate": (datetime.datetime.now() - datetime.timedelta(days=3)).strftime('%Y-%m-%dT00:00:00.000Z')
    }
    try:
        response = requests.get(ORDERS_URL, headers=headers, params=params)
        response.raise_for_status()
        orders = response.json()
        st.subheader("API Response")
        st.json(orders)  # Show raw API response for debugging
        order_list = orders.get("orders", {}).get("elements", [])
        
        if not isinstance(order_list, list):
            st.error("Unexpected API response format. Expected a list of orders.")
            return []
        
        # Sort by orderDate and ensure latest order is used
        order_list = [o for o in order_list if isinstance(o, dict)]
        if not order_list:
            return []
        
        latest_order = max(order_list, key=lambda x: x.get("orderDate", ""))
        return [latest_order]  # Return the latest order as a list
    except requests.RequestException as e:
        st.error(f"Failed to fetch latest order from Walmart API: {str(e)} - Response: {response.text}")
        return []

# Streamlit Dashboard Setup
st.title("Walmart DSV Latest Order Dashboard")
st.sidebar.header("Settings")
refresh = st.sidebar.button("Refresh Data")

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
                        charges = line.get("charges", [])
                        total_line_amount = sum(
                            charge.get("chargeAmount", {}).get("amount", 0)
                            for charge in charges if isinstance(charge, dict)
                        )
                        
                        processed_order.append({
                            "Purchase Order ID": order.get("purchaseOrderId", "N/A"),
                            "Order Date": order.get("orderDate", "N/A"),
                            "Item Name": item.get("productName", "N/A"),
                            "SKU": item.get("sku", "N/A"),
                            "Quantity": line.get("orderLineQuantity", {}).get("amount", 0),
                            "Unit Price ($)": total_line_amount / line.get("orderLineQuantity", {}).get("amount", 1),
                            "Total Line Amount ($)": total_line_amount,
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
        
        # Display Data
        st.subheader("Latest Order Details")
        if not df.empty:
            st.dataframe(
                df,
                hide_index=True,
                column_config={
                    "Purchase Order ID": st.column_config.TextColumn("Purchase Order ID", width="medium"),
                    "Order Date": st.column_config.TextColumn("Order Date", width="medium"),
                    "Item Name": st.column_config.TextColumn("Item Name", width="large"),
                    "SKU": st.column_config.TextColumn("SKU", width="small"),
                    "Quantity": st.column_config.NumberColumn("Quantity", width="small"),
                    "Unit Price ($)": st.column_config.NumberColumn("Unit Price ($)", format="$%.2f", width="small"),
                    "Total Line Amount ($)": st.column_config.NumberColumn("Total Line Amount ($)", format="$%.2f", width="medium"),
                    "Status": st.column_config.TextColumn("Status", width="small")
                }
            )
            
            # Display order summary
            st.subheader("Order Summary")
            total_order_amount = df["Total Line Amount ($)"].sum()
            total_items = df["Quantity"].sum()
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Order Amount", f"${total_order_amount:.2f}")
            with col2:
                st.metric("Total Items", f"{total_items}")
        else:
            st.warning("No latest order found.")
