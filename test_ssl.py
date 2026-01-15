import socket
import ssl

hostname = 'dimond.top'
port = 7860

def test_ssl():
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    print(f"Attempting SSL handshake with {hostname}:{port}...")
    
    try:
        sock = socket.create_connection((hostname, port), timeout=5)
        ssock = context.wrap_socket(sock, server_hostname=hostname)
        print(f"✅ SSL Handshake successful!")
        print(f"   Version: {ssock.version()}")
        print(f"   Cipher: {ssock.cipher()}")
        ssock.close()
        return True
    except ssl.SSLError as e:
        print(f"❌ SSL Error: {e}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
    return False

if __name__ == "__main__":
    test_ssl()
