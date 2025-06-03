from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse

class BarcodeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        if("code="in query and "http" not in query):
            print(f"Received Barcode: {query[5:]}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Barcode Received")

server = HTTPServer(("0.0.0.0", 8080), BarcodeHandler)
print("Server started on port 8080...")
server.serve_forever()
