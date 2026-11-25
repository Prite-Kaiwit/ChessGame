"""สร้าง self-signed TLS certificate ที่มี IP ของเครื่องใน SAN"""

import ipaddress
import socket
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from server.config import CERT_DIR, CERT_FILE, KEY_FILE


def get_lan_ip() -> str:
    """ค้นหา IPv4 ของ LAN โดยไม่ส่งข้อมูลผ่านการเชื่อมต่อ UDP."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 80))
        address = probe.getsockname()[0]
        if not address.startswith("127."):
            return address
    except OSError:
        pass
    finally:
        probe.close()

    candidates = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    for candidate in candidates:
        address = candidate[4][0]
        if not address.startswith("127.") and not address.startswith("169.254."):
            return address
    raise OSError("ไม่พบ IPv4 address ของ LAN สำหรับสร้าง certificate")


def generate_certificate(ip_address: str | None = None) -> str:
    """สร้าง certificate/key และคืน IP ที่ใส่ไว้ใน Subject Alternative Name."""
    address = ip_address or get_lan_ip()
    ip_value = ipaddress.ip_address(address)
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, str(ip_value))]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_value)]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    KEY_FILE.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_FILE.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return str(ip_value)


def ensure_certificate() -> str:
    """ใช้ certificate เดิมถ้ายังตรงกับ IP LAN ปัจจุบัน มิฉะนั้นสร้างใหม่."""
    address = get_lan_ip()
    if CERT_FILE.exists() and KEY_FILE.exists():
        try:
            certificate = x509.load_pem_x509_certificate(CERT_FILE.read_bytes())
            san = certificate.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value
            valid_now = (
                certificate.not_valid_before_utc
                <= datetime.now(timezone.utc)
                < certificate.not_valid_after_utc
            )
            if (
                ipaddress.ip_address(address)
                in san.get_values_for_type(x509.IPAddress)
                and valid_now
            ):
                return address
        except (ValueError, x509.ExtensionNotFound):
            pass
    return generate_certificate(address)


def main() -> None:
    """สร้าง certificate และแสดง URL สำหรับเปิดหน้า camera."""
    ip_address = generate_certificate()
    print("Certificate generated")
    print("Open on your phone: https://{}:8443/camera".format(ip_address))


if __name__ == "__main__":
    main()
