import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from tkinter import simpledialog
import csv
from tkinter.ttk import Combobox
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import queue

from tkinter import filedialog  # for asking the user where to save the file
import reportlab
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Database setup
conn = sqlite3.connect('inventory.db')
c = conn.cursor()

# Create tables
# Create table (or modify your table definition) to include wholesale_price
c.execute('''
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        sku TEXT UNIQUE,
        stock INTEGER,
        purchase_price REAL,
        selling_price REAL,
        wholesale_price REAL,
        company_id INTEGER,  -- Corrected to INTEGER
        FOREIGN KEY (company_id) REFERENCES companies(company_id)  -- Foreign key
    )
''')

c.execute('''CREATE TABLE IF NOT EXISTS companies (
    company_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    daily_price_percentage REAL DEFAULT 0
);''')

c.execute('''CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                total REAL NOT NULL
            )''')

c.execute('''CREATE TABLE IF NOT EXISTS invoice_items (
                invoice_id INTEGER,
                product_id INTEGER,
                quantity INTEGER,
                unit_price REAL,
                total_price REAL,
                historical_purchase_price REAL,
                historical_selling_price REAL,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )''')

conn.commit()

# GUI setup
root = tk.Tk()
root.title("Inventory Management System")
root.geometry("1920x1080")
root.tk.call('source', 'azure.tcl')
root.tk.call("set_theme", "dark")

# Configure styles
style = ttk.Style()
style.configure("Accent.TButton",
                background="green",  # Green background
                foreground="white",    # White text color
                padding=10,            # Optional: add padding to button
                font=("Arial", 12, "bold")  # Optional: change font
)

# Main container
main_frame = ttk.Frame(root)
main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

# Configure grid layout
main_frame.columnconfigure(0, weight=1)
main_frame.columnconfigure(1, weight=1)
main_frame.rowconfigure(1, weight=1)

# Inventory Section (Left)
inventory_frame = ttk.Frame(main_frame)
inventory_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=5, pady=5)

# Header
header_frame = ttk.Frame(inventory_frame, style="Header.TFrame")
header_frame.pack(fill=tk.X, pady=(0, 10))
ttk.Label(header_frame, text="Inventory Management", 
          font=('Helvetica', 14, 'bold'), foreground="white", 
          background="#0078d4",style="Accent.TButton").pack(pady=20)


# Input form
form_frame = ttk.LabelFrame(inventory_frame, text="Product Details", padding=15)
form_frame.pack(fill=tk.X, pady=5)
# Validation function to allow only numbers
def validate_numeric_input(P):
    return P.isdigit() or P == ""  # Allows only integers

def validate_float_input(P):
    try:
        float(P)  # Allows only valid floats
        return True
    except ValueError:
        return P == ""  # Allows empty input

def get_company_names():
    c.execute("SELECT name FROM companies")
    return [row[0] for row in c.fetchall()]

vcmd_int = root.register(validate_numeric_input)
vcmd_float = root.register(validate_float_input)

entries = {}
# Add the wholesale price label to the form; update labels list:
labels = ["Name", "SKU", "Stock", "Purchase Price", "Selling Price", "Wholesale Price", "Company id"]
for i, label in enumerate(labels):
    ttk.Label(form_frame, text=label).grid(row=i, column=0, padx=5, pady=5, sticky=tk.W)
    
    entry = ttk.Entry(form_frame)
    
    # Apply validations as needed. For prices, use float validation:
    if label in ["Stock"]:
        entry.config(validate="key", validatecommand=(vcmd_int, "%P"))
    elif label in ["Purchase Price", "Selling Price", "Wholesale Price"]:
        entry.config(validate="key", validatecommand=(vcmd_float, "%P"))

    entry.grid(row=i, column=1, padx=5, pady=5, sticky=tk.EW)
    entries[label.lower().replace(" ", "_")] = entry

company_names = get_company_names()
company_var = tk.StringVar()
company_combobox = Combobox(form_frame, textvariable=company_var)

# Allow manual input
company_combobox['values'] = company_names
company_combobox.grid(row=6, column=1, padx=5, pady=5, sticky=tk.EW)
company_combobox.set("")  # Default empty value

# Function to update dropdown dynamically
def update_company_list(event):
    typed_text = company_var.get().strip().lower()
    
    if typed_text == "":
        company_combobox['values'] = company_names  # Show all companies if input is empty
    else:
        filtered_companies = [name for name in company_names if typed_text in name.lower()]
        company_combobox['values'] = filtered_companies  # Show only matching companies

company_combobox.bind("<KeyRelease>", update_company_list)  # Trigger filtering while typing

# Buttons
button_frame = ttk.Frame(inventory_frame)
button_frame.pack(fill=tk.X, pady=10)

ttk.Button(button_frame, text="Add Product", command=lambda: add_product(), 
            style="Accent.TButton").pack(side=tk.LEFT, padx=5)
ttk.Button(button_frame, text="Update Product", command=lambda: update_product(),
            style="Accent.TButton").pack(side=tk.LEFT, padx=5)
ttk.Button(button_frame, text="Update Company Prices", command=lambda: update_company_prices(),
            style="Accent.TButton").pack(side=tk.LEFT, padx=5)

# Search bar setup
search_frame = ttk.Frame(inventory_frame)
search_frame.pack(fill=tk.X, pady=(10, 5))

search_label = ttk.Label(search_frame, text="Search:")
search_label.pack(side=tk.LEFT, padx=5)

search_entry = ttk.Entry(search_frame)
search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

# Bind the key release event to trigger search
search_entry.bind("<KeyRelease>", lambda event: search_products(search_entry.get()))




# Functions

def search_products(query):
    view_products(query)  # Call view_products with the search query to filter

# Modify the view_products function to initially show all products

def view_products(search_query=None):
    for row in inventory_tree.get_children():
        inventory_tree.delete(row)

    # Prepare the SQL query to fetch product details along with the company name
    query = """SELECT p.id, p.name, p.sku, p.stock, p.purchase_price, 
                      p.selling_price, p.wholesale_price, COALESCE(c.name, 'No Company') 
               FROM products p
               LEFT JOIN companies c ON p.company_id = c.company_id"""  # LEFT JOIN to include products without a company

    if search_query:
        query += " WHERE p.name LIKE ? OR p.sku LIKE ? OR COALESCE(c.name, '') LIKE ?"
        params = ('%' + search_query + '%', '%' + search_query + '%', '%' + search_query + '%')
        c.execute(query, params)
    else:
        c.execute(query)

    for row in c.fetchall():
        formatted_row = list(row)
        formatted_row[4] = f"{row[4]:.2f}"  # Format Purchase Price
        formatted_row[5] = f"{row[5]:.2f}"  # Format Selling Price
        formatted_row[6] = f"{row[6]:.2f}"  # Format Wholesale Price
        inventory_tree.insert("", tk.END, values=formatted_row)

def refresh_company_dropdown():
    global company_names
    company_names = get_company_names()  # Get updated company names
    company_combobox['values'] = company_names  # Update dropdown options

def get_company_names():
    c.execute("SELECT name FROM companies")
    return [row[0] for row in c.fetchall()]

def add_product():
    entries_data = {key: entry.get() for key, entry in entries.items() if key != 'company_id'}
    company_name = company_var.get().strip()

    if any(not value for value in entries_data.values()):
        messagebox.showwarning("Error", "Please fill all fields except Company (optional)!")
        return

    try:
        if company_name:  # If user entered a company name
            c.execute("SELECT company_id FROM companies WHERE name = ?", (company_name,))
            company_row = c.fetchone()

            if company_row:
                company_id = company_row[0]  # Use existing company ID
            else:
                # Insert new company and get its ID
                c.execute("INSERT INTO companies (name) VALUES (?)", (company_name,))
                conn.commit()
                company_id = c.lastrowid
                refresh_company_dropdown()
        else:
            company_id = None  # Allow NULL company

        # Insert product
        c.execute("""INSERT INTO products 
                    (name, sku, stock, purchase_price, selling_price, wholesale_price, company_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (entries_data['name'], 
                    entries_data['sku'], 
                    entries_data['stock'],
                    entries_data['purchase_price'], 
                    entries_data['selling_price'],
                    entries_data['wholesale_price'],
                    company_id))  # Can be NULL
        
        conn.commit()
        messagebox.showinfo("Success", "Product added!")
        
        for entry in entries.values():
            entry.delete(0, tk.END)
        company_combobox.set("")
        view_products()
    except sqlite3.IntegrityError:
        messagebox.showwarning("Error", "SKU must be unique!")

def add_to_invoice(sku=None):
    if sku is None:
        # Get product from Treeview selection
        selected_item = inventory_tree.selection()
        if not selected_item:
            messagebox.showwarning("Error", "Please select a product from inventory!")
            return
        item_values = inventory_tree.item(selected_item, 'values')
        product_id = item_values[0]
        c.execute("SELECT id, name, sku, stock, purchase_price, selling_price, wholesale_price FROM products WHERE id = ?", (product_id,))
        product = c.fetchone()

    else:
        # Get product by SKU
        c.execute("SELECT id, name, sku, stock, purchase_price, selling_price, wholesale_price FROM products WHERE sku = ?", (sku,))
        product = c.fetchone()
        if not product:
            messagebox.showerror("Error", f"No product found with SKU: {sku}")
            return


    if not product: # this condition check if product came from sku, or inventory tree, without raise an error 
        return
    
    product_id, name, sku, stock, p_price, s_price, w_price = product

    # Check if already in invoice
    for item in invoice_items:
        if item['product_id'] == product_id:
            current_qty = item['quantity'].get()
            item['quantity'].set(current_qty + 1)
            update_invoice_item_total(item)
            calculate_grand_total()  # Make sure to recalc the invoice total.
            return




    # Create invoice item frame
    item_frame = ttk.Frame(invoice_items_frame)
    item_frame.pack(fill=tk.X, pady=2)

    # Product info
    ttk.Label(item_frame, text=name, width=20).grid(row=0, column=0, padx=2)
    ttk.Label(item_frame, text=sku, width=15).grid(row=0, column=1, padx=2)

    # Wholesale option
    wholesale_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(item_frame, text="Wholesale", variable=wholesale_var).grid(row=0, column=2, padx=2)

    # Quantity control
    quantity = tk.IntVar(value=1)
    total = tk.DoubleVar()

    # Function to update price based on wholesale toggle
    def update_total(*args):
        if wholesale_var.get():
            price = float(w_price)
        else:
            price = float(s_price)
        total.set(quantity.get() * price)
        price_label.config(text=f"${price:.2f}")  # Update price label
        calculate_grand_total()

    price_label = ttk.Label(item_frame, text=f"${s_price:.2f}", width=10) #initialy price label
    price_label.grid(row=0, column=3, padx=2)


    # Set trace for quantity and wholesale option
    quantity.trace_add("write", update_total)
    wholesale_var.trace_add("write", update_total)
    update_total()  # Initial call

    spinbox = ttk.Spinbox(item_frame, from_=1, to=100, textvariable=quantity, width=5)
    spinbox.grid(row=0, column=4, padx=2)

    # Total price display
    ttk.Label(item_frame, textvariable=total, width=10).grid(row=0, column=5, padx=2)

    # Delete button
    delete_btn = ttk.Button(item_frame, text="×", width=2,
                           command=lambda f=item_frame, i=product_id: delete_invoice_item(f, i))
    delete_btn.grid(row=0, column=6, padx=2)

    # Store item data
    invoice_items.append({
        'product_id': product_id,
        'frame': item_frame,
        'quantity': quantity,
        'total': total,
        'stock': int(stock),
        'wholesale': wholesale_var,
        'name': name
    })

    calculate_grand_total()


def delete_invoice_item(frame, product_id):
    invoice_items[:] = [item for item in invoice_items if item['product_id'] != product_id]
    frame.destroy()
    calculate_grand_total()

def calculate_grand_total():
    grand_total = sum(item['total'].get() for item in invoice_items)
    invoice_total.config(text=f"${grand_total:.2f}")

def submit_invoice():
    if not invoice_items:
        messagebox.showwarning("Error", "Invoice is empty!")
        return
    
    try:
        # Check stock availability first
        for item in invoice_items:
            if item['quantity'].get() > item['stock']:
                messagebox.showwarning("Error", 
                    f"Not enough stock for ( {item['name']} ) !")
                return
        
        # Start transaction
        conn.execute("BEGIN TRANSACTION")
        
        invoice_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        grand_total = sum(item['total'].get() for item in invoice_items)
        c.execute("INSERT INTO invoices (date, total) VALUES (?, ?)",
                  (invoice_date, grand_total))
        invoice_id = c.lastrowid
        
        # Insert invoice items and update stock
        for item in invoice_items:
            product_id = item['product_id']
            quantity = item['quantity'].get()
            
            # Get current prices from products table including wholesale price
            c.execute("SELECT purchase_price, selling_price, wholesale_price FROM products WHERE id = ?", (product_id,))
            current_purchase_price, current_selling_price, current_wholesale_price = c.fetchone()
            
            # Determine which price to use based on the wholesale flag
            if item['wholesale'].get():
                unit_price = current_wholesale_price
            else:
                unit_price = current_selling_price
            
            total_price = quantity * unit_price
            
            # Update stock
            new_stock = item['stock'] - quantity
            c.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, product_id))
            
            # Insert invoice item with historical prices
            c.execute("""INSERT INTO invoice_items 
                         (invoice_id, product_id, quantity, unit_price, total_price,
                          historical_purchase_price, historical_selling_price)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (invoice_id, product_id, quantity, unit_price, total_price,
                       current_purchase_price, unit_price))
        
        conn.commit()
        messagebox.showinfo("Success", "Invoice processed and stock updated!")
        
        # Clear invoice items
        for item in invoice_items:
            item['frame'].destroy()
        invoice_items.clear()
        calculate_grand_total()
        view_products()
    except Exception as e:
        conn.rollback()
        messagebox.showerror("Error", f"An error occurred: {str(e)}")

def show_invoice_history():
    history_window = tk.Toplevel(root)
    history_window.title("Invoice History")
    history_window.geometry("800x600")
    
    # Export buttons container
    export_frame = ttk.Frame(history_window)
    export_frame.pack(fill=tk.X, padx=10, pady=10)

    export_csv_btn = ttk.Button(export_frame, text="Export to CSV", command=export_history_to_csv)
    export_csv_btn.pack(side=tk.LEFT, padx=5)

    export_pdf_btn = ttk.Button(export_frame, text="Export to PDF", command=export_history_to_pdf)
    export_pdf_btn.pack(side=tk.LEFT, padx=5)

    # Create canvas and scrollbar
    canvas = tk.Canvas(history_window, borderwidth=0)
    scrollbar = ttk.Scrollbar(history_window, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        )
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    # Get invoices grouped by date
    c.execute('''SELECT DATE(date) as invoice_date, 
                COUNT(*) as count, 
                SUM(total) as total 
                FROM invoices 
                GROUP BY DATE(date) 
                ORDER BY DATE(date) DESC''')
    daily_invoices = c.fetchall()
    
    for date_data in daily_invoices:
        date_str, count, daily_total = date_data
        
        # Calculate profit using historical prices
        c.execute('''SELECT ii.quantity, ii.historical_purchase_price, ii.historical_selling_price
                    FROM invoice_items ii
                    JOIN invoices i ON ii.invoice_id = i.id
                    WHERE DATE(i.date) = ?''', (date_str,))
        items = c.fetchall()
        print(        items[0][0])
        total_cost = sum(item[0] * item[1] for item in items)  # quantity * historical_purchase_price
        daily_profit = daily_total - total_cost
        
        # Date header
        date_frame = ttk.Frame(scrollable_frame)
        date_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(date_frame, text=date_str, font=('Helvetica', 12, 'bold')).pack(side=tk.LEFT)
        ttk.Label(date_frame, text=f"{count} invoices - Total: ${daily_total:.2f} - Profit: ${daily_profit:.2f}", 
                 font=('Helvetica', 10)).pack(side=tk.RIGHT)
        
        # Get invoices for this date
        c.execute('''SELECT id, date, total 
                    FROM invoices 
                    WHERE DATE(date) = ? 
                    ORDER BY date DESC''', (date_str,))
        invoices = c.fetchall()
        
        # Create invoice list
        invoice_list = ttk.Frame(scrollable_frame)
        invoice_list.pack(fill=tk.X, padx=20, pady=5)
        
        for invoice in invoices:
            invoice_id, invoice_time, total = invoice
            time_str = datetime.strptime(invoice_time, "%Y-%m-%d %H:%M:%S").strftime("%H:%M:%S")
            
            invoice_frame = ttk.Frame(invoice_list)
            invoice_frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(invoice_frame, text=f"Invoice #{invoice_id}", width=15).pack(side=tk.LEFT)
            ttk.Label(invoice_frame, text=time_str, width=15).pack(side=tk.LEFT)
            ttk.Label(invoice_frame, text=f"${total:.2f}", width=15).pack(side=tk.LEFT)
            
            # View details button
            ttk.Button(invoice_frame, text="Details",
                      command=lambda iid=invoice_id: show_invoice_details(iid)).pack(side=tk.RIGHT)

def show_invoice_details(invoice_id):
    detail_window = tk.Toplevel(root)
    detail_window.title(f"Invoice Details - #{invoice_id}")
    detail_window.geometry("800x400")
    
    # Get the invoice details using historical prices
    c.execute('''SELECT i.date, i.total, ii.product_id, p.name, ii.quantity, 
                 ii.historical_selling_price, ii.historical_purchase_price 
                FROM invoice_items ii
                JOIN products p ON ii.product_id = p.id
                JOIN invoices i ON ii.invoice_id = i.id
                WHERE ii.invoice_id = ?''', (invoice_id,))
    items = c.fetchall()

    # Create frame for showing invoice details
    invoice_frame = ttk.Frame(detail_window)
    invoice_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    
    # Add invoice date and total
    invoice_date = items[0][0]
    total_revenue = items[0][1]

    date_label = ttk.Label(invoice_frame, text=f"Date: {invoice_date}", font=('Helvetica', 12, 'bold'))
    date_label.pack(anchor=tk.W)
    
    total_label = ttk.Label(invoice_frame, text=f"Total Revenue: ${total_revenue:.2f}", font=('Helvetica', 12, 'bold'))
    total_label.pack(anchor=tk.W, pady=10)

    # Calculate the profit using historical prices
    total_revenue = 0.0
    total_cost = 0.0
    for item in items:
        historical_selling_price = item[5]
        quantity = item[4]
        historical_purchase_price = item[6]
        
        # Accumulate totals using historical prices
        total_revenue += historical_selling_price * quantity
        total_cost += historical_purchase_price * quantity

    # Calculate the profit
    invoice_profit = total_revenue - total_cost

    # Display the profit before the table
    profit_label = ttk.Label(invoice_frame, text=f"Profit: ${invoice_profit:.2f}", font=('Helvetica', 12, 'bold'))
    profit_label.pack(anchor=tk.W)

    # Create Treeview for item details
    tree = ttk.Treeview(invoice_frame, columns=("Product ID", "Name", "Quantity", "Historical Selling Price", "Historical Purchase Price", "Total"), show="headings")
    
    # Define headings
    tree.heading("Product ID", text="Product ID")
    tree.heading("Name", text="Name")
    tree.heading("Quantity", text="Quantity")
    tree.heading("Historical Selling Price", text="Selling Price (at sale)")
    tree.heading("Historical Purchase Price", text="Purchase Price (at sale)")
    tree.heading("Total", text="Total")

    # Set column widths
    tree.column("Product ID", width=100, anchor="center")
    tree.column("Name", width=150, anchor="center")
    tree.column("Quantity", width=100, anchor="center")
    tree.column("Historical Selling Price", width=100, anchor="center")
    tree.column("Historical Purchase Price", width=100, anchor="center")
    tree.column("Total", width=100, anchor="center")

    # Insert items into the Treeview using historical prices
    for item in items:
        product_id = item[2]
        product_name = item[3]
        quantity = item[4]
        historical_selling_price = item[5]
        historical_purchase_price = item[6]
        
        # Calculate the total for this item using historical selling price
        item_total = historical_selling_price * quantity
        
        # Insert item into the treeview
        tree.insert("", tk.END, values=(
            product_id, 
            product_name, 
            quantity, 
            f"${historical_selling_price:.2f}", 
            f"${historical_purchase_price:.2f}", 
            f"${item_total:.2f}")
        )
    
    # Display the Treeview
    tree.pack(fill=tk.BOTH, expand=True)

def update_product():
    selected_item = inventory_tree.selection()
    if not selected_item:
        messagebox.showwarning("Error", "Please select a product to update!")
        return

    item_values = inventory_tree.item(selected_item, 'values')
    product_id = item_values[0]
    current_stock = int(item_values[3])
    current_purchase_price = float(item_values[4])
    current_selling_price = float(item_values[5])
    current_wholesale_price = float(item_values[6])  # Get current wholesale price

    # Create a custom dialog for updates
    update_window = tk.Toplevel(root)
    update_window.title(f"Update Product - {item_values[1]}")
    update_window.geometry("300x500")  # Increased height for wholesale price
    
    # Make the dialog modal
    update_window.transient(root)
    update_window.grab_set()
    
    # Create and pack widgets
    
    ttk.Label(update_window, text="Additional Stock:").pack(pady=5)
    stock_entry = ttk.Entry(update_window)
    stock_entry.pack(pady=5)
    stock_entry.insert(0, "0")  # Default value
    
    ttk.Label(update_window, text=f"Current Purchase Price: ${current_purchase_price}").pack(pady=5)
    ttk.Label(update_window, text="New Purchase Price:").pack(pady=5)
    purchase_price_entry = ttk.Entry(update_window)
    purchase_price_entry.pack(pady=5)
    purchase_price_entry.insert(0, str(current_purchase_price))
    
    ttk.Label(update_window, text=f"Current Selling Price: ${current_selling_price}").pack(pady=5)
    ttk.Label(update_window, text="New Selling Price:").pack(pady=5)
    selling_price_entry = ttk.Entry(update_window)
    selling_price_entry.pack(pady=5)
    selling_price_entry.insert(0, str(current_selling_price))

    ttk.Label(update_window, text=f"Current Wholesale Price: ${current_wholesale_price}").pack(pady=5) #Current Wholesale Price
    ttk.Label(update_window, text="New Wholesale Price:").pack(pady=5) #Wholesale Price
    wholesale_price_entry = ttk.Entry(update_window)
    wholesale_price_entry.pack(pady=5)
    wholesale_price_entry.insert(0, str(current_wholesale_price))

    def validate_and_update():
        try:
            # Get and validate additional stock
            additional_stock = int(stock_entry.get() or "0")
            
            # Get and validate prices
            new_purchase_price = float(purchase_price_entry.get())
            new_selling_price = float(selling_price_entry.get())
            new_wholesale_price = float(wholesale_price_entry.get()) # Get new wholesale price

            
            if new_purchase_price < 0 or new_selling_price < 0 or new_wholesale_price < 0:
                raise ValueError("Prices cannot be negative")
            
            if new_selling_price < new_purchase_price:
                if not messagebox.askyesno("Warning", 
                    "Selling price is lower than purchase price. Continue anyway?"):
                    return
            
            # Calculate new stock
            updated_stock = current_stock + additional_stock
            
            # Update database
            c.execute("""UPDATE products 
                        SET stock = ?, 
                            purchase_price = ?, 
                            selling_price = ?,
                            wholesale_price = ?
                        WHERE id = ?""", 
                     (updated_stock, new_purchase_price, new_selling_price, new_wholesale_price, product_id)) # Update whoesale price
            conn.commit()
            
            messagebox.showinfo("Success", 
                f"""Product updated successfully!
                Stock: {current_stock} → {updated_stock}
                Purchase Price: ${current_purchase_price:.2f} → ${new_purchase_price:.2f}
                Selling Price: ${current_selling_price:.2f} → ${new_selling_price:.2f}
                Wholesale Price: ${current_wholesale_price:.2f} → ${new_wholesale_price:.2f}""")
            
            update_window.destroy()
            view_products()  # Refresh product list
            
        except ValueError as e:
            messagebox.showerror("Error", "Please enter valid numbers for all fields!")

    # Add update button
    ttk.Button(update_window, text="Update", 
               command=validate_and_update, 
               style="Accent.TButton").pack(pady=20)

    # Center the window
    update_window.update_idletasks()
    width = update_window.winfo_width()
    height = update_window.winfo_height()
    x = (update_window.winfo_screenwidth() // 2) - (width // 2)
    y = (update_window.winfo_screenheight() // 2) - (height // 2)
    update_window.geometry(f'{width}x{height}+{x}+{y}')

def export_history_to_csv():
    # Ask the user for the filename to save CSV
    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv")],
        title="Save Invoice History as CSV"
    )
    if not file_path:
        return

    # Query daily invoices and calculate profit per day
    c.execute('''SELECT DATE(date) as invoice_date, 
                COUNT(*) as count, 
                SUM(total) as total 
                FROM invoices 
                GROUP BY DATE(date) 
                ORDER BY DATE(date) DESC''')
    daily_invoices = c.fetchall()

    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Write headers
        writer.writerow(["Invoice Date", "Invoice Count", "Total Revenue", "Daily Profit"])
        for date_data in daily_invoices:
            date_str, count, daily_total = date_data
            # Calculate profit for each date
            total_cost = 0.0
            c.execute('''SELECT ii.quantity, p.purchase_price 
                        FROM invoice_items ii
                        JOIN products p ON ii.product_id = p.id
                        JOIN invoices i ON ii.invoice_id = i.id
                        WHERE DATE(i.date) = ?''', (date_str,))
            items = c.fetchall()
            for item in items:
                quantity, purchase_price = item
                total_cost += purchase_price * quantity
            daily_profit = daily_total - total_cost
            writer.writerow([date_str, count, f"${daily_total:.2f}", f"${daily_profit:.2f}"])
    
    messagebox.showinfo("Export Successful", f"Invoice history exported to {file_path}")

def export_history_to_pdf():
    # Ask the user for the filename to save PDF
    file_path = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF files", "*.pdf")],
        title="Save Invoice History as PDF"
    )
    if not file_path:
        return

    # Create a canvas using ReportLab
    c_pdf = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    y = height - 50

    # Title
    c_pdf.setFont("Helvetica-Bold", 16)
    c_pdf.drawString(50, y, "Invoice History")
    y -= 30

    # Table headers
    c_pdf.setFont("Helvetica-Bold", 12)
    headers = ["Invoice Date", "Invoice Count", "Total Revenue", "Daily Profit"]
    x_positions = [50, 200, 350, 500]
    for x, header in zip(x_positions, headers):
        c_pdf.drawString(x, y, header)
    y -= 20

    c_pdf.setFont("Helvetica", 10)
    # Query daily invoices and calculate profit per day
    c.execute('''SELECT DATE(date) as invoice_date, 
                COUNT(*) as count, 
                SUM(total) as total 
                FROM invoices 
                GROUP BY DATE(date) 
                ORDER BY DATE(date) DESC''')
    daily_invoices = c.fetchall()

    for date_data in daily_invoices:
        date_str, count, daily_total = date_data
        total_cost = 0.0
        c.execute('''SELECT ii.quantity, p.purchase_price 
                    FROM invoice_items ii
                    JOIN products p ON ii.product_id = p.id
                    JOIN invoices i ON ii.invoice_id = i.id
                    WHERE DATE(i.date) = ?''', (date_str,))
        items = c.fetchall()
        for item in items:
            quantity, purchase_price = item
            total_cost += purchase_price * quantity
        daily_profit = daily_total - total_cost
        
        # Write row values
        row_values = [date_str, str(count), f"${daily_total:.2f}", f"${daily_profit:.2f}"]
        for x, value in zip(x_positions, row_values):
            c_pdf.drawString(x, y, value)
        y -= 20
        if y < 50:  # Create a new page if needed
            c_pdf.showPage()
            y = height - 50

    c_pdf.save()
    messagebox.showinfo("Export Successful", f"Invoice history exported to {file_path}")

def draf():
    # def view_products():
    #     for row in inventory_tree.get_children():
    #         inventory_tree.delete(row)
    print("tset")
    #     c.execute("SELECT * FROM products")
    #     for row in c.fetchall():
    #         inventory_tree.insert("", tk.END, values=row)

def update_company_prices():
    # Create a new modal window for updating company prices.
    update_win = tk.Toplevel(root)
    update_win.title("Update Company Prices")
    update_win.geometry("400x500")
    update_win.transient(root)
    update_win.grab_set()
    update_win.update_idletasks()
    width = update_win.winfo_width()
    height = update_win.winfo_height()
    x = (update_win.winfo_screenwidth() // 2) - (width // 2)
    y = (update_win.winfo_screenheight() // 2) - (height // 2)
    update_win.geometry(f'{width}x{height}+{x}+{y}')

    # --- Company search section ---
    ttk.Label(update_win, text="Search Company:").pack(pady=5)
    search_company_var = tk.StringVar()
    search_entry = ttk.Entry(update_win, textvariable=search_company_var)
    search_entry.pack(pady=5, padx=10, fill=tk.X)
    
    # Listbox to display matching companies.
    company_listbox = tk.Listbox(update_win, height=5)
    company_listbox.pack(padx=10, pady=5, fill=tk.BOTH)
    
    def search_company(*args):
        search_term = search_company_var.get()
        # Clear the listbox.
        company_listbox.delete(0, tk.END)
        # Retrieve companies matching the search term.
        query = "SELECT company_id, name FROM companies WHERE name LIKE ?"
        c.execute(query, ('%' + search_term + '%',))
        companies = c.fetchall()
        for comp in companies:
            # Display as "id: Company Name" so that later you can extract the id.
            company_listbox.insert(tk.END, f"{comp[0]}: {comp[1]}")
    search_company()
    # Call search_company whenever the search text changes.
    search_company_var.trace_add("write", search_company)
    
    # --- Price percentage entries ---
    ttk.Label(update_win, text="Purchase Price Percentage (%):").pack(pady=5)
    purchase_pct_entry = ttk.Entry(update_win)
    purchase_pct_entry.pack(pady=5, padx=10, fill=tk.X)
    
    ttk.Label(update_win, text="Selling Price Percentage (%):").pack(pady=5)
    selling_pct_entry = ttk.Entry(update_win)
    selling_pct_entry.pack(pady=5, padx=10, fill=tk.X)
    
    ttk.Label(update_win, text="Wholesale Price Percentage (%):").pack(pady=5)
    wholesale_pct_entry = ttk.Entry(update_win)
    wholesale_pct_entry.pack(pady=5, padx=10, fill=tk.X)
    
    # --- Function to update product prices ---
    def apply_updates():
        # Make sure a company is selected.
        try:
            selected = company_listbox.get(company_listbox.curselection())
            # The company id is the part before the colon.
            company_id = int(selected.split(":")[0])
        except tk.TclError:
            messagebox.showerror("Error", "Please select a company from the list.")
            return

        # Validate percentage inputs.
        try:
            purchase_pct = float(purchase_pct_entry.get())
            selling_pct = float(selling_pct_entry.get())
            wholesale_pct = float(wholesale_pct_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid percentage values (e.g., 10 or -5).")
            return

        # Retrieve all products for the selected company.
        c.execute("SELECT id, purchase_price, selling_price, wholesale_price FROM products WHERE company_id = ?", (company_id,))
        products = c.fetchall()

        # Update each product’s prices.
        for prod in products:
            prod_id, p_price, s_price, w_price = prod
            # Calculate new prices. (For an increase, the factor is (1 + percentage/100). For a decrease, a negative percentage works correctly.)
            new_p_price = p_price * (1 + purchase_pct / 100)
            new_s_price = s_price * (1 + selling_pct / 100)
            new_w_price = w_price * (1 + wholesale_pct / 100)
            
            c.execute(
                """UPDATE products 
                   SET purchase_price = ?, selling_price = ?, wholesale_price = ? 
                   WHERE id = ?""",
                (new_p_price, new_s_price, new_w_price, prod_id)
            )
        conn.commit()
        messagebox.showinfo("Success", "Product prices updated successfully!")
        update_win.destroy()
        view_products()  # Refresh the product list display.

    ttk.Button(update_win, text="Apply Updates", command=apply_updates, style="Accent.TButton").pack(pady=20)

def update_invoice_item_total(item):
    # Determine the appropriate price (for example, use selling_price)
    # This sample assumes you want to use the selling price.
    c.execute("SELECT selling_price FROM products WHERE id = ?", (item['product_id'],))
    price = c.fetchone()[0]
    total = price * item['quantity'].get()
    item['total'].set(total)

barcode_queue = queue.Queue()

# ------------------------------------------------------------------------------
# Barcode HTTP Server Handler
# ------------------------------------------------------------------------------
class BarcodeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        if "code=" in query and "http" not in query:
            sku = query[5:]  # assumes the query is exactly like "code=..."
            print(f"Received Barcode: {sku}")
            # Put the SKU into the queue for the Tkinter thread to process
            barcode_queue.put(sku)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Barcode Received")

def run_barcode_server():
    server = HTTPServer(("0.0.0.0", 8080), BarcodeHandler)
    print("Barcode server started on port 8080...")
    server.serve_forever()

# Start the barcode server in a separate daemon thread.
barcode_thread = threading.Thread(target=run_barcode_server, daemon=True)
barcode_thread.start()

# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
def process_barcode(sku):
    # Query the database for a product with this SKU.
    c.execute("SELECT id, name, sku, stock, purchase_price, selling_price, wholesale_price FROM products WHERE sku = ?", (sku,))
    product = c.fetchone()
    
    if product:
        product_id, name, sku, stock, p_price, s_price, w_price = product
        # Check if product already exists in the current invoice.
        for item in invoice_items:
            if item['product_id'] == product_id:
                # Increase the quantity by 1.
                current_qty = item['quantity'].get()
                item['quantity'].set(current_qty + 1)
                update_invoice_item_total(item)
                calculate_grand_total()  # Make sure to recalc the invoice total.
                return
        
        # Otherwise, add this product as a new invoice item.
        add_to_invoice(sku)
    else:
        # Product not found: open a small window to add a new product.
        open_new_product_window(sku)


def open_new_product_window(sku):
    # This window will allow the user to enter details for a new product.
    new_product_win = tk.Toplevel(root)
    new_product_win.title("New Product")
    new_product_win.geometry("300x700")  # Increased height for company
    new_product_win.transient(root)
    new_product_win.grab_set()
    screen_width = new_product_win.winfo_screenwidth()
    screen_height = new_product_win.winfo_screenheight()
    window_width = 300  # Same as set in geometry
    window_height = 700  # Same as set in geometry # Increased height
    x_position = (screen_width // 2) - (window_width // 2)
    y_position = (screen_height // 2) - (window_height // 2)
    new_product_win.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")

    ttk.Label(new_product_win, text="SKU:").pack(pady=5)
    sku_entry = ttk.Entry(new_product_win)
    sku_entry.pack(pady=5, padx=10, fill=tk.X)
    sku_entry.insert(0, sku)
    sku_entry.config(state='disabled')  # Disable editing of the barcode

    ttk.Label(new_product_win, text="Name:").pack(pady=5)
    name_entry = ttk.Entry(new_product_win)
    name_entry.pack(pady=5, padx=10, fill=tk.X)

    ttk.Label(new_product_win, text="Stock:").pack(pady=5)
    stock_entry = ttk.Entry(new_product_win)
    stock_entry.pack(pady=5, padx=10, fill=tk.X)
    stock_entry.config(validate="key", validatecommand=(vcmd_int, "%P"))

    ttk.Label(new_product_win, text="Purchase Price:").pack(pady=5)
    purchase_entry = ttk.Entry(new_product_win)
    purchase_entry.pack(pady=5, padx=10, fill=tk.X)
    purchase_entry.config(validate="key", validatecommand=(vcmd_float, "%P"))

    ttk.Label(new_product_win, text="Selling Price:").pack(pady=5)
    selling_entry = ttk.Entry(new_product_win)
    selling_entry.pack(pady=5, padx=10, fill=tk.X)
    selling_entry.config(validate="key", validatecommand=(vcmd_float, "%P"))
    
    ttk.Label(new_product_win, text="Wholesale Price:").pack(pady=5)
    wholesale_entry = ttk.Entry(new_product_win)
    wholesale_entry.pack(pady=5, padx=10, fill=tk.X)
    wholesale_entry.config(validate="key", validatecommand=(vcmd_float, "%P"))

    # --- Company Combobox (Identical to main form) ---
    ttk.Label(new_product_win, text="Company:").pack(pady=5)
    company_var_new = tk.StringVar()  # Use a DIFFERENT variable name
    company_combobox_new = Combobox(new_product_win, textvariable=company_var_new)
    company_combobox_new['values'] = company_names
    company_combobox_new.pack(pady=5, padx=10, fill=tk.X)
    company_combobox_new.set("")  # Default empty

    def update_company_list_new(event):
        typed_text = company_var_new.get().strip().lower()
        if typed_text == "":
            company_combobox_new['values'] = company_names
        else:
            filtered_companies = [name for name in company_names if typed_text in name.lower()]
            company_combobox_new['values'] = filtered_companies

    company_combobox_new.bind("<KeyRelease>", update_company_list_new)
    # --- End Company Combobox ---
    def save_new_product():
        name = name_entry.get()
        company_name = company_var_new.get().strip() # Get company name

        try:
            stock = int(stock_entry.get())
            purchase_price = float(purchase_entry.get())
            selling_price = float(selling_entry.get())
            wholesale_price = float(wholesale_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for stock and prices!")
            return

        if not name:
            messagebox.showerror("Error", "Please enter a product name!")
            return
        
        try:
             # --- Company ID Handling (Same logic as add_product) ---
            if company_name:
                c.execute("SELECT company_id FROM companies WHERE name = ?", (company_name,))
                company_row = c.fetchone()
                if company_row:
                    company_id = company_row[0]
                else:
                    c.execute("INSERT INTO companies (name) VALUES (?)", (company_name,))
                    conn.commit()
                    company_id = c.lastrowid
                    refresh_company_dropdown()  # Refresh main dropdown
            else:
                company_id = None
            # --- End Company ID Handling ---

            c.execute("""INSERT INTO products (name, sku, stock, purchase_price, selling_price, wholesale_price, company_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (name, sku, stock, purchase_price, selling_price, wholesale_price, company_id)) # Include company_id
            conn.commit()
            messagebox.showinfo("Success", "Product added!")
            new_product_win.destroy()
            add_to_invoice(sku)  # Add the new product to the invoice
            view_products()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "A product with this SKU already exists!")

    ttk.Button(new_product_win, text="Save Product", command=save_new_product, style="Accent.TButton").pack(pady=20)

# ------------------------------------------------------------------------------
# Function to Periodically Check the Barcode Queue
# ------------------------------------------------------------------------------
def check_barcode_queue():
    try:
        while True:
            sku = barcode_queue.get_nowait()
            process_barcode(sku)
    except queue.Empty:
        pass
    # Schedule the next check after 100 milliseconds.
    root.after(100, check_barcode_queue)

# Start checking the barcode queue.
check_barcode_queue()






# Inventory List
tree_frame = ttk.Frame(inventory_frame)
tree_frame.pack(fill=tk.BOTH, expand=True)

columns = ("id", "name", "sku", "stock", "purchase_price", "selling_price", "wholesale_price", "company_name")
inventory_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

headers = ["ID", "Name", "SKU", "Stock", "Purchase Price", "Selling Price","Wholesale Price", "Company"]
widths = [20, 100, 100, 60, 60, 60,60,100]
for col, header, width in zip(columns, headers, widths):
    inventory_tree.heading(col, text=header)
    inventory_tree.column(col, width=width, anchor="center")
    if col == "id":
        inventory_tree.column(col, width=0, anchor="center")

inventory_tree.grid(row=0, column=0, sticky=tk.NSEW)

scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=inventory_tree.yview)
scrollbar.grid(row=0, column=1, sticky=tk.NS)
inventory_tree.configure(yscrollcommand=scrollbar.set)

tree_frame.grid_columnconfigure(0, weight=1)
tree_frame.grid_rowconfigure(0, weight=1)

# Invoice Section (Right)
invoice_frame = ttk.Frame(main_frame)
invoice_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=5, pady=5)

# Invoice Header
invoice_header = ttk.Frame(invoice_frame, style="Header.TFrame")
invoice_header.pack(fill=tk.X, pady=(0, 10))
ttk.Label(invoice_header, text="Current Invoice", 
         font=('Helvetica', 14, 'bold'), foreground="white", 
         background="#0078d4",style="Accent.TButton").pack(pady=10)

# Invoice Items Canvas
invoice_canvas = tk.Canvas(invoice_frame, borderwidth=0)
invoice_scrollbar = ttk.Scrollbar(invoice_frame, orient="vertical", command=invoice_canvas.yview)
invoice_items_frame = ttk.Frame(invoice_canvas)

invoice_items_frame.bind(
    "<Configure>",
    lambda e: invoice_canvas.configure(
        scrollregion=invoice_canvas.bbox("all")
    )
)

invoice_canvas.create_window((0, 0), window=invoice_items_frame, anchor="nw")
invoice_canvas.configure(yscrollcommand=invoice_scrollbar.set)

invoice_canvas.pack(side="left", fill="both", expand=True)
invoice_scrollbar.pack(side="right", fill="y")




# Invoice Controls
invoice_controls = ttk.Frame(invoice_frame)
invoice_controls.pack(fill=tk.X, pady=10)

ttk.Button(invoice_controls, text="Add Selected Item", 
          command=lambda: add_to_invoice()).pack(side=tk.LEFT, padx=5)
ttk.Button(invoice_controls, text="Submit Invoice", 
          command=submit_invoice, style="Accent.TButton").pack(side=tk.RIGHT, padx=5)

# Total Display
total_frame = ttk.Frame(invoice_frame)
total_frame.pack(fill=tk.X, pady=10)

ttk.Label(total_frame, text="Total:", font=('Helvetica', 12, 'bold')).pack(side=tk.LEFT)
invoice_total = ttk.Label(total_frame, text="$0.00", font=('Helvetica', 12, 'bold'))
invoice_total.pack(side=tk.RIGHT)

# Invoice items storage
invoice_items = []


# Add history button to main UI
history_button = ttk.Button(main_frame, text="View History", command=show_invoice_history)
history_button.grid(row=0, column=1, sticky="ne", padx=10, pady=10)

view_products()

# Run the app
root.mainloop()
