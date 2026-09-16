import ast
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

import dotenv
import numpy as np
import pandas as pd
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import Engine, create_engine
from sqlalchemy.sql import text

MAX_QUOTE_ROUNDS = 2
MAX_CUSTOMER_ROUNDS = 2

INVENTORY_REQUEST_LIMIT = 4
CUSTOMER_REQUEST_LIMIT = 3
COMMERCIAL_REQUEST_LIMIT = 10
ADVISOR_REQUEST_LIMIT = 4
ORCHESTRATOR_REQUEST_LIMIT = 25

# Create an SQLite database
db_engine = create_engine("sqlite:///munder_difflin.db")

# List containing the different kinds of papers 
paper_supplies = [
    # Paper Types (priced per sheet unless specified)
    {"item_name": "A4 paper",                         "category": "paper",        "unit_price": 0.05},
    {"item_name": "Letter-sized paper",              "category": "paper",        "unit_price": 0.06},
    {"item_name": "Cardstock",                        "category": "paper",        "unit_price": 0.15},
    {"item_name": "Colored paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Glossy paper",                     "category": "paper",        "unit_price": 0.20},
    {"item_name": "Matte paper",                      "category": "paper",        "unit_price": 0.18},
    {"item_name": "Recycled paper",                   "category": "paper",        "unit_price": 0.08},
    {"item_name": "Eco-friendly paper",               "category": "paper",        "unit_price": 0.12},
    {"item_name": "Poster paper",                     "category": "paper",        "unit_price": 0.25},
    {"item_name": "Banner paper",                     "category": "paper",        "unit_price": 0.30},
    {"item_name": "Kraft paper",                      "category": "paper",        "unit_price": 0.10},
    {"item_name": "Construction paper",               "category": "paper",        "unit_price": 0.07},
    {"item_name": "Wrapping paper",                   "category": "paper",        "unit_price": 0.15},
    {"item_name": "Glitter paper",                    "category": "paper",        "unit_price": 0.22},
    {"item_name": "Decorative paper",                 "category": "paper",        "unit_price": 0.18},
    {"item_name": "Letterhead paper",                 "category": "paper",        "unit_price": 0.12},
    {"item_name": "Legal-size paper",                 "category": "paper",        "unit_price": 0.08},
    {"item_name": "Crepe paper",                      "category": "paper",        "unit_price": 0.05},
    {"item_name": "Photo paper",                      "category": "paper",        "unit_price": 0.25},
    {"item_name": "Uncoated paper",                   "category": "paper",        "unit_price": 0.06},
    {"item_name": "Butcher paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Heavyweight paper",                "category": "paper",        "unit_price": 0.20},
    {"item_name": "Standard copy paper",              "category": "paper",        "unit_price": 0.04},
    {"item_name": "Bright-colored paper",             "category": "paper",        "unit_price": 0.12},
    {"item_name": "Patterned paper",                  "category": "paper",        "unit_price": 0.15},

    # Product Types (priced per unit)
    {"item_name": "Paper plates",                     "category": "product",      "unit_price": 0.10},  # per plate
    {"item_name": "Paper cups",                       "category": "product",      "unit_price": 0.08},  # per cup
    {"item_name": "Paper napkins",                    "category": "product",      "unit_price": 0.02},  # per napkin
    {"item_name": "Disposable cups",                  "category": "product",      "unit_price": 0.10},  # per cup
    {"item_name": "Table covers",                     "category": "product",      "unit_price": 1.50},  # per cover
    {"item_name": "Envelopes",                        "category": "product",      "unit_price": 0.05},  # per envelope
    {"item_name": "Sticky notes",                     "category": "product",      "unit_price": 0.03},  # per sheet
    {"item_name": "Notepads",                         "category": "product",      "unit_price": 2.00},  # per pad
    {"item_name": "Invitation cards",                 "category": "product",      "unit_price": 0.50},  # per card
    {"item_name": "Flyers",                           "category": "product",      "unit_price": 0.15},  # per flyer
    {"item_name": "Party streamers",                  "category": "product",      "unit_price": 0.05},  # per roll
    {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},  # per roll
    {"item_name": "Paper party bags",                 "category": "product",      "unit_price": 0.25},  # per bag
    {"item_name": "Name tags with lanyards",          "category": "product",      "unit_price": 0.75},  # per tag
    {"item_name": "Presentation folders",             "category": "product",      "unit_price": 0.50},  # per folder

    # Large-format items (priced per unit)
    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
    {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},

    # Specialty papers
    {"item_name": "100 lb cover stock",               "category": "specialty",    "unit_price": 0.50},
    {"item_name": "80 lb text paper",                 "category": "specialty",    "unit_price": 0.40},
    {"item_name": "250 gsm cardstock",                "category": "specialty",    "unit_price": 0.30},
    {"item_name": "220 gsm poster paper",             "category": "specialty",    "unit_price": 0.35},
]

# Given below are some utility functions you can use to implement your multi-agent system

def generate_sample_inventory(paper_supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    """
    Generate inventory for exactly a specified percentage of items from the full paper supply list.

    This function randomly selects exactly `coverage` × N items from the `paper_supplies` list,
    and assigns each selected item:
    - a random stock quantity between 200 and 800,
    - a minimum stock level between 50 and 150.

    The random seed ensures reproducibility of selection and stock levels.

    Args:
        paper_supplies (list): A list of dictionaries, each representing a paper item with
                               keys 'item_name', 'category', and 'unit_price'.
        coverage (float, optional): Fraction of items to include in the inventory (default is 0.4, or 40%).
        seed (int, optional): Random seed for reproducibility (default is 137).

    Returns:
        pd.DataFrame: A DataFrame with the selected items and assigned inventory values, including:
                      - item_name
                      - category
                      - unit_price
                      - current_stock
                      - min_stock_level
    """
    # Ensure reproducible random output
    np.random.seed(seed)

    # Calculate number of items to include based on coverage
    num_items = int(len(paper_supplies) * coverage)

    # Randomly select item indices without replacement
    selected_indices = np.random.choice(
        range(len(paper_supplies)),
        size=num_items,
        replace=False
    )

    # Extract selected items from paper_supplies list
    selected_items = [paper_supplies[i] for i in selected_indices]

    # Construct inventory records
    inventory = []
    for item in selected_items:
        inventory.append({
            "item_name": item["item_name"],
            "category": item["category"],
            "unit_price": item["unit_price"],
            "current_stock": np.random.randint(200, 800),  # Realistic stock range
            "min_stock_level": np.random.randint(50, 150)  # Reasonable threshold for reordering
        })

    # Return inventory as a pandas DataFrame
    return pd.DataFrame(inventory)

def init_database(db_engine: Engine, seed: int = 137) -> Engine:    
    """
    Set up the Munder Difflin database with all required tables and initial records.

    This function performs the following tasks:
    - Creates the 'transactions' table for logging stock orders and sales
    - Loads customer inquiries from 'quote_requests.csv' into a 'quote_requests' table
    - Loads previous quotes from 'quotes.csv' into a 'quotes' table, extracting useful metadata
    - Generates a random subset of paper inventory using `generate_sample_inventory`
    - Inserts initial financial records including available cash and starting stock levels

    Args:
        db_engine (Engine): A SQLAlchemy engine connected to the SQLite database.
        seed (int, optional): A random seed used to control reproducibility of inventory stock levels.
                              Default is 137.

    Returns:
        Engine: The same SQLAlchemy engine, after initializing all necessary tables and records.

    Raises:
        Exception: If an error occurs during setup, the exception is printed and raised.
    """
    try:
        # ----------------------------
        # 1. Create an empty 'transactions' table schema
        # ----------------------------
        transactions_schema = pd.DataFrame({
            "id": [],
            "item_name": [],
            "transaction_type": [],  # 'stock_orders' or 'sales'
            "units": [],             # Quantity involved
            "price": [],             # Total price for the transaction
            "transaction_date": [],  # ISO-formatted date
        })
        transactions_schema.to_sql("transactions", db_engine, if_exists="replace", index=False)

        # Set a consistent starting date
        initial_date = datetime(2025, 1, 1).isoformat()

        # ----------------------------
        # 2. Load and initialize 'quote_requests' table
        # ----------------------------
        quote_requests_df = pd.read_csv("quote_requests.csv")
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 3. Load and transform 'quotes' table
        # ----------------------------
        quotes_df = pd.read_csv("quotes.csv")
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = initial_date

        # Unpack metadata fields (job_type, order_size, event_type) if present
        if "request_metadata" in quotes_df.columns:
            quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
            quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("job_type", ""))
            quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda x: x.get("order_size", ""))
            quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("event_type", ""))

        # Retain only relevant columns
        quotes_df = quotes_df[[
            "request_id",
            "total_amount",
            "quote_explanation",
            "order_date",
            "job_type",
            "order_size",
            "event_type"
        ]]
        quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 4. Generate inventory and seed stock
        # ----------------------------
        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)

        # Seed initial transactions
        initial_transactions = []

        # Add a starting cash balance via a dummy sales transaction
        initial_transactions.append({
            "item_name": None,
            "transaction_type": "sales",
            "units": None,
            "price": 50000.0,
            "transaction_date": initial_date,
        })

        # Add one stock order transaction per inventory item
        for _, item in inventory_df.iterrows():
            initial_transactions.append({
                "item_name": item["item_name"],
                "transaction_type": "stock_orders",
                "units": item["current_stock"],
                "price": item["current_stock"] * item["unit_price"],
                "transaction_date": initial_date,
            })

        # Commit transactions to database
        pd.DataFrame(initial_transactions).to_sql("transactions", db_engine, if_exists="append", index=False)

        # Save the inventory reference table
        inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)

        return db_engine

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

def create_transaction(
    item_name: str,
    transaction_type: str,
    quantity: int,
    price: float,
    date: Union[str, datetime],
) -> int:
    """
    This function records a transaction of type 'stock_orders' or 'sales' with a specified
    item name, quantity, total price, and transaction date into the 'transactions' table of the database.

    Args:
        item_name (str): The name of the item involved in the transaction.
        transaction_type (str): Either 'stock_orders' or 'sales'.
        quantity (int): Number of units involved in the transaction.
        price (float): Total price of the transaction.
        date (str or datetime): Date of the transaction in ISO 8601 format.

    Returns:
        int: The ID of the newly inserted transaction.

    Raises:
        ValueError: If `transaction_type` is not 'stock_orders' or 'sales'.
        Exception: For other database or execution errors.
    """
    try:
        # Convert datetime to ISO string if necessary
        date_str = date.isoformat() if isinstance(date, datetime) else date

        # Validate transaction type
        if transaction_type not in {"stock_orders", "sales"}:
            raise ValueError("Transaction type must be 'stock_orders' or 'sales'")

        # Prepare transaction record as a single-row DataFrame
        transaction = pd.DataFrame([{
            "item_name": item_name,
            "transaction_type": transaction_type,
            "units": quantity,
            "price": price,
            "transaction_date": date_str,
        }])

        # Insert the record into the database
        transaction.to_sql("transactions", db_engine, if_exists="append", index=False)

        # Fetch and return the ID of the inserted row
        result = pd.read_sql("SELECT last_insert_rowid() as id", db_engine)
        return int(result.iloc[0]["id"])

    except Exception as e:
        print(f"Error creating transaction: {e}")
        raise

def get_all_inventory(as_of_date: str) -> Dict[str, int]:
    """
    Retrieve a snapshot of available inventory as of a specific date.

    This function calculates the net quantity of each item by summing 
    all stock orders and subtracting all sales up to and including the given date.

    Only items with positive stock are included in the result.

    Args:
        as_of_date (str): ISO-formatted date string (YYYY-MM-DD) representing the inventory cutoff.

    Returns:
        Dict[str, int]: A dictionary mapping item names to their current stock levels.
    """
    # SQL query to compute stock levels per item as of the given date
    query = """
        SELECT
            item_name,
            SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END) as stock
        FROM transactions
        WHERE item_name IS NOT NULL
        AND transaction_date <= :as_of_date
        GROUP BY item_name
        HAVING stock > 0
    """

    # Execute the query with the date parameter
    result = pd.read_sql(query, db_engine, params={"as_of_date": as_of_date})

    # Convert the result into a dictionary {item_name: stock}
    return dict(zip(result["item_name"], result["stock"]))

def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
    """
    Retrieve the stock level of a specific item as of a given date.

    This function calculates the net stock by summing all 'stock_orders' and 
    subtracting all 'sales' transactions for the specified item up to the given date.

    Args:
        item_name (str): The name of the item to look up.
        as_of_date (str or datetime): The cutoff date (inclusive) for calculating stock.

    Returns:
        pd.DataFrame: A single-row DataFrame with columns 'item_name' and 'current_stock'.
    """
    # Convert date to ISO string format if it's a datetime object
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    # SQL query to compute net stock level for the item
    stock_query = """
        SELECT
            item_name,
            COALESCE(SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END), 0) AS current_stock
        FROM transactions
        WHERE item_name = :item_name
        AND transaction_date <= :as_of_date
    """

    # Execute query and return result as a DataFrame
    return pd.read_sql(
        stock_query,
        db_engine,
        params={"item_name": item_name, "as_of_date": as_of_date},
    )

def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """
    Estimate the supplier delivery date based on the requested order quantity and a starting date.

    Delivery lead time increases with order size:
        - ≤10 units: same day
        - 11–100 units: 1 day
        - 101–1000 units: 4 days
        - >1000 units: 7 days

    Args:
        input_date_str (str): The starting date in ISO format (YYYY-MM-DD).
        quantity (int): The number of units in the order.

    Returns:
        str: Estimated delivery date in ISO format (YYYY-MM-DD).
    """
    # Debug log (comment out in production if needed)
    print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity} from date string '{input_date_str}'")

    # Attempt to parse the input date
    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        # Fallback to current date on format error
        print(f"WARN (get_supplier_delivery_date): Invalid date format '{input_date_str}', using today as base.")
        input_date_dt = datetime.now()

    # Determine delivery delay based on quantity
    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7

    # Add delivery days to the starting date
    delivery_date_dt = input_date_dt + timedelta(days=days)

    # Return formatted delivery date
    return delivery_date_dt.strftime("%Y-%m-%d")

def get_cash_balance(as_of_date: Union[str, datetime]) -> float:
    """
    Calculate the current cash balance as of a specified date.

    The balance is computed by subtracting total stock purchase costs ('stock_orders')
    from total revenue ('sales') recorded in the transactions table up to the given date.

    Args:
        as_of_date (str or datetime): The cutoff date (inclusive) in ISO format or as a datetime object.

    Returns:
        float: Net cash balance as of the given date. Returns 0.0 if no transactions exist or an error occurs.
    """
    try:
        # Convert date to ISO format if it's a datetime object
        if isinstance(as_of_date, datetime):
            as_of_date = as_of_date.isoformat()

        # Query all transactions on or before the specified date
        transactions = pd.read_sql(
            "SELECT * FROM transactions WHERE transaction_date <= :as_of_date",
            db_engine,
            params={"as_of_date": as_of_date},
        )

        # Compute the difference between sales and stock purchases
        if not transactions.empty:
            total_sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
            total_purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
            return float(total_sales - total_purchases)

        return 0.0

    except Exception as e:
        print(f"Error getting cash balance: {e}")
        return 0.0


def generate_financial_report(as_of_date: Union[str, datetime]) -> Dict:
    """
    Generate a complete financial report for the company as of a specific date.

    This includes:
    - Cash balance
    - Inventory valuation
    - Combined asset total
    - Itemized inventory breakdown
    - Top 5 best-selling products

    Args:
        as_of_date (str or datetime): The date (inclusive) for which to generate the report.

    Returns:
        Dict: A dictionary containing the financial report fields:
            - 'as_of_date': The date of the report
            - 'cash_balance': Total cash available
            - 'inventory_value': Total value of inventory
            - 'total_assets': Combined cash and inventory value
            - 'inventory_summary': List of items with stock and valuation details
            - 'top_selling_products': List of top 5 products by revenue
    """
    # Normalize date input
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    # Get current cash balance
    cash = get_cash_balance(as_of_date)

    # Get current inventory snapshot
    inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
    inventory_value = 0.0
    inventory_summary = []

    # Compute total inventory value and summary by item
    for _, item in inventory_df.iterrows():
        stock_info = get_stock_level(item["item_name"], as_of_date)
        stock = stock_info["current_stock"].iloc[0]
        item_value = stock * item["unit_price"]
        inventory_value += item_value

        inventory_summary.append({
            "item_name": item["item_name"],
            "stock": stock,
            "unit_price": item["unit_price"],
            "value": item_value,
        })

    # Identify top-selling products by revenue
    top_sales_query = """
        SELECT item_name, SUM(units) as total_units, SUM(price) as total_revenue
        FROM transactions
        WHERE transaction_type = 'sales' AND transaction_date <= :date
        GROUP BY item_name
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    top_sales = pd.read_sql(top_sales_query, db_engine, params={"date": as_of_date})
    top_selling_products = top_sales.to_dict(orient="records")

    return {
        "as_of_date": as_of_date,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
        "top_selling_products": top_selling_products,
    }


def search_quote_history(search_terms: List[str], limit: int = 5) -> List[Dict]:
    """
    Retrieve a list of historical quotes that match any of the provided search terms.

    The function searches both the original customer request (from `quote_requests`) and
    the explanation for the quote (from `quotes`) for each keyword. Results are sorted by
    most recent order date and limited by the `limit` parameter.

    Args:
        search_terms (List[str]): List of terms to match against customer requests and explanations.
        limit (int, optional): Maximum number of quote records to return. Default is 5.

    Returns:
        List[Dict]: A list of matching quotes, each represented as a dictionary with fields:
            - original_request
            - total_amount
            - quote_explanation
            - job_type
            - order_size
            - event_type
            - order_date
    """
    conditions = []
    params = {}

    # Build SQL WHERE clause using LIKE filters for each search term
    for i, term in enumerate(search_terms):
        param_name = f"term_{i}"
        conditions.append(
            f"(LOWER(qr.response) LIKE :{param_name} OR "
            f"LOWER(q.quote_explanation) LIKE :{param_name})"
        )
        params[param_name] = f"%{term.lower()}%"

    # Combine conditions; fallback to always-true if no terms provided
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Final SQL query to join quotes with quote_requests
    query = f"""
        SELECT
            qr.response AS original_request,
            q.total_amount,
            q.quote_explanation,
            q.job_type,
            q.order_size,
            q.event_type,
            q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT {limit}
    """

    # Execute parameterized query
    with db_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result]

########################
########################
########################
# YOUR MULTI AGENT STARTS HERE
########################
########################
########################


# Set up and load your env parameters and instantiate your model.
dotenv.load_dotenv()
api_key = os.getenv("UDACITY_OPENAI_API_KEY")

if not api_key:
    raise ValueError(
        "UDACITY_OPENAI_API_KEY is missing. Add it to your .env file."
    )

model_name = os.getenv(
    "UDACITY_OPENAI_MODEL",
    "gpt-4o-mini",
)

provider = OpenAIProvider(
    base_url="https://openai.vocareum.com/v1",
    api_key=api_key,
)

model = OpenAIChatModel(
    model_name,
    provider=provider,
)

"""Set up tools for your agents to use, these should be methods that combine the database functions above
 and apply criteria to them to ensure that the flow of the system is correct."""

def extract_required_by(request: str) -> str | None:
    """
    Extract an explicit customer delivery deadline.

    Args:
        request: The customer request to extract the delivery deadline from.

    Returns:
        The delivery deadline in ISO format (YYYY-MM-DD).
    """
    match = re.search(
        r"(January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2},\s+\d{4}",
        request,
        re.IGNORECASE,
    )

    if not match:
        return None

    return datetime.strptime(
        match.group(0),
        "%B %d, %Y",
    ).strftime("%Y-%m-%d")

def to_json_safe(value):
    """
    Convert NumPy/Pandas values into JSON-serializable Python values.
    Args:
        value: The value to convert.
    Returns:
        The JSON-serializable value.
    """

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            key: to_json_safe(val)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [
            to_json_safe(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            to_json_safe(item)
            for item in value
        ]

    return value

def normalize_item_name(item_name: str) -> str | None:
    """
    Map customer wording to canonical catalog item names.

    Args:
        item_name: The name of the item to normalize.

    Returns:
        The normalized item name.
    """

    name = item_name.lower().strip()

    # Exact match first.
    for item in paper_supplies:
        if item["item_name"].lower() == name:
            return item["item_name"]

    # Important specialty matches first.
    if "washi" in name:
        return "Decorative adhesive tape (washi tape)"

    if "250 gsm" in name and "cardstock" in name:
        return "250 gsm cardstock"

    if "220 gsm" in name and "poster" in name:
        return "220 gsm poster paper"

    if "100 lb" in name and ("cover" in name or "cardstock" in name):
        return "100 lb cover stock"

    if "24x36" in name or "24 x 36" in name or "poster board" in name:
        return "Large poster paper (24x36 inches)"

    # Reject unsupported paper sizes rather than pretending they are A4.
    if "a3" in name or "a5" in name:
        return None

    # General paper aliases.
    if "glossy" in name:
        return "Glossy paper"

    if "matte" in name:
        return "Matte paper"

    if "construction" in name:
        return "Construction paper"

    if "recycled" in name and "paper" in name:
        return "Recycled paper"

    if "cardstock" in name:
        return "Cardstock"

    if "colored" in name or "colourful" in name or "colorful" in name:
        return "Colored paper"

    if "printer paper" in name or "printing paper" in name:
        if "a4" in name:
            return "A4 paper"
        return "Standard copy paper"

    if "a4" in name and "paper" in name:
        return "A4 paper"

    if "streamer" in name:
        return "Party streamers"

    if "napkin" in name:
        return "Paper napkins"

    if "paper plate" in name:
        return "Paper plates"

    if "paper cup" in name:
        return "Paper cups"

    if "flyer" in name:
        return "Flyers"

    if "envelope" in name:
        return "Envelopes"

    if "poster" in name:
        return "Poster paper"

    return None

# Tools for inventory agent
def get_catalog_item(item_name: str) -> Dict:
    """
    Look up an exact canonical item from the company product catalog.

    Agents should use canonical item names before inventory or
    transaction operations.

    Args:
        item_name: The name of the item to look up.

    Returns:
        A dictionary containing the catalog item information.
    """
    canonical_name = normalize_item_name(item_name)
    for item in paper_supplies:
        if item["item_name"].lower() == item_name.lower():
            return item

    if canonical_name is None:
        return {
            "supported": False,
            "original_name": item_name,
        }

    for item in paper_supplies:
        if item["item_name"] == canonical_name:
            return {
                **item,
                "supported": True,
                "original_name": item_name,
            }

    return {
        "supported": False,
        "original_name": item_name,
    }

@dataclass
class RequestContext:
    request_date: str
    required_by: Optional[str]

    # Workflow state
    inventory_done: bool = False
    sale_attempted: bool = False
    sale_done: bool = False
    advisor_done: bool = False

    # Negotiation state
    quote_rounds: int = 0
    customer_rounds: int = 0

    # Accepted quote state
    quoted_items: Dict[str, Dict] = field(default_factory=dict)
    quoted_total: float = 0.0
    fulfilled_items: List[str] = field(default_factory=list)

def check_inventory(
    ctx: RunContext[RequestContext],
    item_name: str,
    quantity: int,
) -> Dict:
    """
    Check current inventory and determine whether a shortage can be
    replenished before the customer's deadline.

    Args:
        ctx: The context of the request.
        item_name: The name of the item to check.
        quantity: The quantity of the item to check.

    Returns:
        A dictionary containing the inventory information.
    """
    item = get_catalog_item(item_name)

    if not item.get("supported", True):
        return {
            "item_name": item_name,
            "supported": False,
            "fulfillable": False,
            "reason": "The requested item is not in our product catalog.",
        }
    request_date = ctx.deps.request_date
    required_by = ctx.deps.required_by

    canonical_name = item["item_name"]
    stock_df = get_stock_level(canonical_name, request_date)
    current_stock = int(stock_df["current_stock"].iloc[0])

    shortage = max(0, quantity - current_stock)

    if shortage == 0:
        return {
            "original_item_name": item_name,
            "item_name": canonical_name,
            "supported": True,
            "current_stock": current_stock,
            "requested_quantity": quantity,
            "shortage": 0,
            "reorder_required": False,
            "fulfillable": True,
            "reason": "Enough inventory is currently available.",
        }

    supplier_delivery_date = get_supplier_delivery_date(
        request_date,
        shortage,
    )

    reorder_cost = shortage * item["unit_price"]
    cash_balance = get_cash_balance(request_date)

    can_afford = cash_balance >= reorder_cost
    arrives_on_time = (
        True
        if required_by is None
        else supplier_delivery_date <= required_by
    )

    if not arrives_on_time:
        reason = (
            "The required additional stock cannot arrive before "
            "the requested delivery date."
        )
    elif not can_afford:
        reason = "The required inventory replenishment cannot be funded."
    else:
        reason = (
            "Current inventory is insufficient, but the shortage "
            "can be replenished in time."
        )

    return {
        "original_item_name": item_name,
        "item_name": canonical_name,
        "supported": True,
        "current_stock": current_stock,
        "requested_quantity": quantity,
        "shortage": shortage,
        "reorder_required": True,
        "supplier_delivery_date": supplier_delivery_date,
        "reorder_cost": reorder_cost,
        "can_afford_reorder": can_afford,
        "arrives_on_time": arrives_on_time,
        "fulfillable": can_afford and arrives_on_time,
        "reason": reason,
    }

def check_inventory_batch(
    ctx: RunContext[RequestContext],
    items: List[Dict],
) -> Dict:
    """
    Check inventory feasibility for all requested items in one tool call.

    Each item must contain:
    - item_name
    - quantity

    Args:
        ctx: The context of the request.
        items: A list of dictionaries containing the items to check.

    Returns:
        A dictionary containing the inventory feasibility results.
    """
    results = []

    for item in items:
        result = check_inventory(
            ctx,
            item_name=item["item_name"],
            quantity=int(item["quantity"]),
        )
        results.append(result)

    return {
        "items": to_json_safe(results),
        "all_fulfillable": all(
            item.get("fulfillable", False)
            for item in results
        ),
    }

def reorder_inventory(
    item_name: str,
    quantity: int,
    order_date: str,
) -> Dict:
    """
    Replenish inventory when enough cash is available.
    The stock transaction is dated when the supplier delivers it.
    Args:
        item_name: The name of the item to reorder.
        quantity: The quantity of the item to reorder.
        order_date: The date to order the item.
    Returns:
        A dictionary containing the reorder information.
    """
    item = get_catalog_item(item_name)

    if not item.get("supported", True):
        return {
            "success": False,
            "reason": "Unsupported catalog item.",
        }

    if quantity <= 0:
        return {
            "success": False,
            "reason": "Quantity must be positive.",
        }

    cost = quantity * item["unit_price"]
    cash_balance = get_cash_balance(order_date)

    if cost > cash_balance:
        return {
            "success": False,
            "reason": "Insufficient cash for replenishment.",
        }

    arrival_date = get_supplier_delivery_date(
        order_date,
        quantity,
    )

    transaction_id = create_transaction(
        item_name=item_name,
        transaction_type="stock_orders",
        quantity=quantity,
        price=cost,
        date=order_date,
    )

    return {
        "success": True,
        "transaction_id": transaction_id,
        "item_name": item_name,
        "quantity": quantity,
        "arrival_date": arrival_date,
    }

# Tools for quoting agent
def search_historical_quotes(
    search_terms: List[str],
    limit: int = 5,
) -> List[Dict]:
    """
    Search historical quotes and remove obviously invalid quote records.
    Args:
        search_terms: The terms to search for in the quote history.
        limit: The maximum number of quotes to return.
    Returns:
        A list of dictionaries containing the historical quotes.
    """
    quotes = search_quote_history(
        search_terms=search_terms,
        limit=limit,
    )

    valid_quotes = [
        quote
        for quote in quotes
        if quote.get("total_amount") is not None
        and quote["total_amount"] > 0
    ]

    return to_json_safe(valid_quotes)

def calculate_quote(
    ctx: RunContext[RequestContext],
    items: List[Dict],
    search_terms: List[str],
) -> Dict:
    """
    Calculate a quote from catalog prices, apply a deterministic
    bulk discount, and consult historical quotes when available.
    Args:
        ctx: The context of the request.
        items: The items to quote.
        search_terms: The terms to search for in the quote history.
    Returns:
        A dictionary containing the quote information.
    """

    quote_items = []
    subtotal = 0.0
    total_quantity = 0

    for requested_item in items:
        item = get_catalog_item(requested_item["item_name"])

        if not item.get("supported", True):
            return {
                "success": False,
                "reason": f"Unsupported item: {requested_item['item_name']}",
            }

        quantity = int(requested_item["quantity"])
        line_subtotal = round(
            item["unit_price"] * quantity,
            2,
        )

        quote_items.append(
            {
                "item_name": item["item_name"],
                "quantity": quantity,
                "unit_price": item["unit_price"],
                "line_subtotal": line_subtotal,
            }
        )

        subtotal += line_subtotal
        total_quantity += quantity

    # Explicit bulk-discount policy.
    if total_quantity >= 1000:
        discount_rate = 0.10
    elif total_quantity >= 500:
        discount_rate = 0.07
    elif total_quantity >= 100:
        discount_rate = 0.05
    else:
        discount_rate = 0.0

    subtotal = round(subtotal, 2)
    discount_amount = round(
        subtotal * discount_rate,
        2,
    )
    total = round(
        subtotal - discount_amount,
        2,
    )

    # Search one broad term at a time because the starter
    # search_quote_history combines multiple terms with AND.
    historical_quotes = []

    for term in search_terms[:3]:
        historical_quotes = search_historical_quotes(
            [term],
            limit=3,
        )

        if historical_quotes:
            break

    # Allocate the same discount across individual line items.
    running_total = 0.0

    for index, quote_item in enumerate(quote_items):
        if index == len(quote_items) - 1:
            line_total = round(
                total - running_total,
                2,
            )
        else:
            line_total = round(
                quote_item["line_subtotal"] * (1 - discount_rate),
                2,
            )
            running_total += line_total

        quote_item["line_total"] = line_total

    # Save the authoritative quote for sale finalization.
    ctx.deps.quoted_items = {
        item["item_name"]: {
            "quantity": item["quantity"],
            "sale_price": item["line_total"],
        }
        for item in quote_items
    }

    ctx.deps.quoted_total = total
    ctx.deps.fulfilled_items = []

    return {
        "success": True,
        "items": quote_items,
        "subtotal": subtotal,
        "total_quantity": total_quantity,
        "bulk_discount_rate": discount_rate,
        "discount_amount": discount_amount,
        "total": total,
        "historical_quotes_found": len(historical_quotes),
        "historical_quotes": historical_quotes,
    }

# Tools for ordering agent
def fulfill_order_item(
    ctx: RunContext[RequestContext],
    item_name: str,
    quantity: int,
) -> Dict:
    """
    Finalize the sale of one item only if sufficient inventory exists.
    Args:
        ctx: The context of the request.
        item_name: The name of the item to fulfill.
        quantity: The quantity of the item to fulfill.
    Returns:
        A dictionary containing the fulfillment information.
    """
    item = get_catalog_item(item_name)

    if not item.get("supported", True):
        return {
            "success": False,
            "reason": "Unsupported catalog item.",
        }

    canonical_name = item["item_name"]
    quoted_item = ctx.deps.quoted_items.get(canonical_name)

    if quoted_item is None:
        return {
            "success": False,
            "reason": "This item is not part of the accepted quote.",
        }

    if quantity != quoted_item["quantity"]:
        return {
            "success": False,
            "reason": "Quantity does not match the accepted quote.",
        }

    sale_price = float(
        quoted_item["sale_price"]
    )

    request_date = ctx.deps.request_date
    required_by = ctx.deps.required_by

    stock_df = get_stock_level(
        canonical_name,
        request_date,
    )

    current_stock = int(
        stock_df["current_stock"].iloc[0]
    )

    shortage = max(0, quantity - current_stock)
    fulfillment_date = request_date

    # Replenish shortage when it can arrive before the deadline.
    if shortage > 0:
        delivery_date = get_supplier_delivery_date(
            request_date,
            shortage,
        )

        if required_by and delivery_date > required_by:
            return {
                "success": False,
                "reason": "Required stock cannot arrive before the deadline.",
            }

        reorder_result = reorder_inventory(
            canonical_name,
            shortage,
            request_date,
        )

        if not reorder_result["success"]:
            return reorder_result

        fulfillment_date = delivery_date

    transaction_id = create_transaction(
        item_name=canonical_name,
        transaction_type="sales",
        quantity=quantity,
        price=sale_price,
        date=request_date,
    )

    if canonical_name not in ctx.deps.fulfilled_items:
        ctx.deps.fulfilled_items.append(
            canonical_name
        )

    ctx.deps.sale_done = (
        len(ctx.deps.fulfilled_items)
        == len(ctx.deps.quoted_items)
    )

    return {
        "success": True,
        "transaction_id": transaction_id,
        "item_name": canonical_name,
        "quantity": quantity,
        "sale_price": sale_price,
        "fulfillment_date": fulfillment_date,
    }

# Tool for business advisor agent
def get_business_health(as_of_date: str) -> Dict:
    """
    Return internal financial and inventory information
    for business analysis.
    Args:
        as_of_date: The date to get the business health for.
    Returns:
        A dictionary containing the business health.
    """
    business_health = {
        "financial_report": generate_financial_report(as_of_date),
        "cash_balance": get_cash_balance(as_of_date),
        "inventory": get_all_inventory(as_of_date),
    }

    return to_json_safe(business_health)

# Set up your agents and create an orchestration agent that will manage them.
def create_multi_agent_system():
    """
    Set up the agents and create an orchestration agent that will manage them.
    """

    customer_agent = Agent(
        model,
        instructions="""
            You represent the customer during negotiation with Beaver's Choice
            Paper Company.

            Preserve the customer's original products, quantities,
            delivery deadline, event context, and explicit constraints.

            Your response MUST begin with exactly one of:

            ACCEPT:
            COUNTER:
            REJECT:

            IMPORTANT PRICING RULES:

            - Never invent a budget, target price, maximum price,
            or willingness-to-pay that the customer did not state.
            - Never counter merely because a lower price would be nice.
            - If the customer's original request contains no explicit
            budget or price constraint, and the quote:
                * contains the requested products and quantities,
                * can meet the delivery deadline,
                * includes a bulk discount,
            then ACCEPT the quote.

            - COUNTER only when the original customer request provides
            a real price/budget constraint that the quote does not meet.
            - REJECT only when an explicit customer constraint cannot
            reasonably be satisfied.

            On negotiation round 2:
            - You MUST choose ACCEPT or REJECT.
            - Do not make another counteroffer.

            If the original request does not explicitly contain a dollar amount,
            you are forbidden from mentioning or creating any budget, target price,
            maximum price, or price ceiling.
            Do not silently change products, quantities, or deadlines.
            Do not ask the real user whether they want to proceed.
            Keep the response concise.
            """)

    inventory_agent = Agent(
        model,
        deps_type=RequestContext,
        tools=[
            check_inventory_batch,
        ],
        instructions="""
            You are the Inventory and Procurement Agent.
            Extract every distinct requested product and its quantity from the request.
            Then:

            1. Call check_inventory_batch exactly once with all requested items.
            2. Use the returned results to determine fulfillment feasibility.
            3. Return a concise inventory assessment immediately.
            4. Do not call another tool after check_inventory_batch.
            5. Do not repeat the inventory assessment.

            Do not purchase inventory.
            Do not create transactions.
            Do not invent stock quantities, supplier dates, or financial data.""")

    commercial_agent = Agent(
        model,
        tools=[
            search_historical_quotes,
            fulfill_order_item,
            calculate_quote,
        ],
        instructions="""
            You are the Commercial Agent.
            You have two separate modes.
            QUOTE MODE:
            - Call calculate_quote exactly once.
            - Include every requested item and quantity.
            - Use broad customer context such as job, event, or product
            category as historical search terms.
            - Use the returned price exactly.
            - Clearly report:
                subtotal,
                bulk discount percentage,
                discount amount,
                final total.
            - Do not calculate your own alternative price.
            - Do not create transactions.
            SALE MODE:
            - Finalize only an accepted quote.
            - Call fulfill_order_item once for every quoted item.
            - Use the exact quoted quantities.
            - Do not invent or modify prices.
            - If any fulfillment tool fails, report the failure honestly.

            Never include transaction IDs in your response.
            Never expose database IDs, tool names, internal function results,
            cash balances, margins, or internal system messages.
            """)

    business_advisor_agent = Agent(
        model,
        tools=[
            get_business_health,
        ],
        instructions="""
            You are the internal Business Advisor.

            Analyze transactions, inventory, cash, and financial reports.

            Recommend improvements related to:
            - inventory efficiency
            - recurring shortages
            - purchasing
            - pricing
            - revenue

            Your analysis is internal.
            Do not expose confidential financial information to customers.
            Do not execute purchases or sales yourself.
            """)

    async def delegate_inventory(
        ctx: RunContext[RequestContext],
        request: str,
    ) -> str:
        """
        Delegate inventory assessment work.
        Args:
            ctx: The context of the request.
            request: The request to evaluate or negotiate.
        Returns:
            The response from the inventory agent.
        """
        if ctx.deps.inventory_done:
            return "Inventory assessment already completed. Do not call this agent again."

        ctx.deps.inventory_done = True

        print("[ORCHESTRATOR] -> Inventory Agent")

        result = await inventory_agent.run(
            request,
            deps=ctx.deps,
            usage_limits=UsageLimits(
                request_limit=INVENTORY_REQUEST_LIMIT,
                tool_calls_limit=1,
            ),
        )

        return str(result.output)


    async def delegate_commercial(
        ctx: RunContext[RequestContext],
        request: str,
        task: str,
    ) -> str:
        """
        Delegate quotation or sales work.
        Args:
            ctx: The context of the request.
            request: The request to evaluate or negotiate.
        Returns:
            The response from the commercial agent.
        """
        task = task.lower().strip()

        if task == "quote":
            # Allow at most 2 quote rounds.
            if ctx.deps.quote_rounds >= MAX_QUOTE_ROUNDS:
                return "Maximum quote rounds reached. Do not request another quote."

            ctx.deps.quote_rounds += 1

            prompt = f"""
            QUOTE MODE
            Quote round: {ctx.deps.quote_rounds}

            Generate or revise the quote only.
            Do not finalize or record a sale.

            {request}
            """

        elif task == "sale":
            if ctx.deps.sale_attempted:
                return "Sale finalization already attempted. Do not call again."

            ctx.deps.sale_attempted = True

            accepted_items = [
                {
                    "item_name": item_name,
                    "quantity": details["quantity"],
                }
                for item_name, details in ctx.deps.quoted_items.items()
            ]

            prompt = f"""
            SALE MODE

            The accepted quote below is authoritative:

            {accepted_items}

            Call fulfill_order_item exactly once for EACH item above.
            Use exactly the item names and quantities shown above.
            Do not change quantities.
            Do not add or remove products.
            Do not generate another quote.

            Original workflow context:
            {request}
            """

        else:
            return "Invalid task. Use 'quote' or 'sale'."

        print(f"[ORCHESTRATOR] -> Commercial Agent ({task})")

        result = await commercial_agent.run(
            prompt,
            deps=ctx.deps,
            usage_limits=UsageLimits(
                request_limit=COMMERCIAL_REQUEST_LIMIT,
            ),
        )

        return str(result.output)


    async def delegate_customer(ctx: RunContext[RequestContext], request: str) -> str:
        """
        Ask the customer agent to evaluate or negotiate an offer.
        Args:
            ctx: The context of the request.
            request: The request to evaluate or negotiate.
        Returns:
            The response from the customer agent.
        """
        if ctx.deps.quote_rounds == 0:
            return "No quote exists to evaluate. Do not call the Customer Agent."

        if ctx.deps.customer_rounds >= MAX_CUSTOMER_ROUNDS:
            return "Customer negotiation already completed. Do not call again."

        ctx.deps.customer_rounds += 1

        print("[ORCHESTRATOR] -> Customer Agent")

        prompt = f"""
        Negotiation round: {ctx.deps.customer_rounds}

        {request}
        """

        result = await customer_agent.run(
            prompt,
            usage_limits=UsageLimits(request_limit=3),
        )

        return str(result.output)


    async def delegate_business_analysis(ctx: RunContext[RequestContext], request: str) -> str:
        """
        Delegate internal business analysis.
        Args:
            ctx: The context of the request.
            request: The request to evaluate or negotiate.
        Returns:
            The response from the business advisor agent.
        """
        if ctx.deps.advisor_done:
            return "Business analysis already completed. Do not call again."

        ctx.deps.advisor_done = True

        print("[ORCHESTRATOR] -> Business Advisor")

        result = await business_advisor_agent.run(
            request,
            usage_limits=UsageLimits(
                request_limit=ADVISOR_REQUEST_LIMIT,
                tool_calls_limit=1,
            ),
        )

        return str(result.output)

    orchestrator_agent = Agent(
        model,
        deps_type=RequestContext,
        tools=[
            delegate_inventory,
            delegate_commercial,
            delegate_customer,
            delegate_business_analysis,
        ],
        instructions="""
            You are the Orchestrator Agent for Beaver's Choice Paper Company.
            Coordinate the specialized worker agents to process one customer request.

            Follow this workflow strictly:
            1. Call the Inventory Agent exactly once.
            2. Treat the Inventory Agent's feasibility result as authoritative. Do not reinterpret stock quantities or supplier dates.
            3. If the complete order cannot be fulfilled:
            return a customer-facing explanation and stop.
            4. If fulfillment is feasible: call the Commercial Agent with task="quote".
            5. Send that quote to the Customer Agent.
            6. If the Customer Agent responds ACCEPT: call the Commercial Agent with task="sale".
            7. If the Customer Agent responds COUNTER: 
            call the Commercial Agent one more time with task="quote",
            passing the counteroffer context.
            Then call the Customer Agent one final time.
            8. On the second customer round: the decision must be ACCEPT or REJECT.
            9. If ACCEPT: finalize the sale exactly once.
            10. If REJECT: return a concise customer-facing response and stop.
            11. Optionally call the Business Advisor after a successful sale.

            For every successful sale, the final customer-facing response must include
            the purchased items, quantities, accepted prices, final order total,
            and delivery information from the Commercial Agent's result.

            Never omit the accepted order total from a successful-sale response.
            Never exceed two quote rounds.
            Never exceed two customer rounds.
            Never restart the workflow.
            Never claim an order was successfully completed unless
            the Commercial Agent confirms successful fulfillment.

            Do not expose internal cash balances, assets, margins,
            database details, or internal business analysis.
            """)

    return {
        "customer": customer_agent,
        "inventory": inventory_agent,
        "commercial": commercial_agent,
        "business_advisor": business_advisor_agent,
        "orchestrator": orchestrator_agent,
    }

# Run your test scenarios by writing them here. Make sure to keep track of them.

def run_test_scenarios():
    
    print("Initializing Database...")
    init_database(db_engine)
    try:
        quote_requests_sample = pd.read_csv("quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return

    # Get initial state
    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    report = generate_financial_report(initial_date)
    current_cash = report["cash_balance"]
    current_inventory = report["inventory_value"]

    ############
    ############
    ############
    # INITIALIZE YOUR MULTI AGENT SYSTEM HERE
    agents = create_multi_agent_system()
    orchestrator_agent = agents["orchestrator"]
    ############
    ############
    ############

    results = []
    for idx, row in quote_requests_sample.iterrows():
        request_date = row["request_date"].strftime("%Y-%m-%d")

        print(f"\n=== Request {idx+1} ===")
        print(f"Context: {row['job']} organizing {row['event']}")
        print(f"Request Date: {request_date}")
        print(f"Cash Balance: ${current_cash:.2f}")
        print(f"Inventory Value: ${current_inventory:.2f}")

        ############
        ############
        ############
        # USE YOUR MULTI AGENT SYSTEM TO HANDLE THE REQUEST
        request_with_date = (
            f"{row['request']} "
            f"(Date of request: {request_date})"
        )
        required_by = extract_required_by(row['request'])

        contextual_request = f"""
        Customer role: {row['job']}
        Order size: {row['need_size']}
        Event: {row['event']}
        Required delivery date: {required_by or 'not specified'}

        Customer request:
        {request_with_date}
        """

        request_context = RequestContext(
            request_date=request_date,
            required_by=required_by,
        )

        # Save cash before processing this request.
        cash_before = current_cash

        result = orchestrator_agent.run_sync(
            contextual_request,
            deps=request_context,
            usage_limits=UsageLimits(
                request_limit=ORCHESTRATOR_REQUEST_LIMIT,
            ),
        )
        response = str(result.output)
        ############
        ############
        ############

        # response = call_your_multi_agent_system(request_with_date)

        # Update state
        report = generate_financial_report(request_date)
        current_cash = report["cash_balance"]
        current_inventory = report["inventory_value"]

        cash_after = current_cash
        cash_change = cash_after - cash_before

        print(f"Response: {response}")
        print(f"Updated Cash: ${current_cash:.2f}")
        print(f"Updated Inventory: ${current_inventory:.2f}")

        results.append(
            {
                "request_id": idx + 1,
                "request_date": request_date,
                "cash_balance": current_cash,
                "cash_before": round(cash_before, 2),
                "cash_after": round(cash_after, 2),
                "cash_change": round(cash_change, 2),
                "inventory_value": current_inventory,
                "fulfilled": request_context.sale_done,
                "quote_rounds": request_context.quote_rounds,
                "customer_rounds": request_context.customer_rounds,
                "response": response,
            }
        )

        time.sleep(1)

    # Final report
    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    print("\n===== FINAL FINANCIAL REPORT =====")
    print(f"Final Cash: ${final_report['cash_balance']:.2f}")
    print(f"Final Inventory: ${final_report['inventory_value']:.2f}")

    # Save results
    pd.DataFrame(results).to_csv("test_results.csv", index=False)
    return results


if __name__ == "__main__":
    results = run_test_scenarios()
