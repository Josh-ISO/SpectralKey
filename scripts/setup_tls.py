"""Generate a localhost-only development certificate; does not change system trust."""
import ipaddress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID


def generate(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    certificate, keyfile = directory / 'localhost.pem', directory / 'localhost-key.pem'
    if certificate.exists() and keyfile.exists():
        return certificate, keyfile
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SpectralKey localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=90))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
                x509.IPAddress(ipaddress.ip_address('::1'))]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / 'localhost.cer').write_bytes(cert.public_bytes(serialization.Encoding.DER))
    return certificate, keyfile


if __name__ == '__main__':
    cert, _ = generate(Path(__file__).resolve().parent.parent / '.tls')
    print(f'Created/using {cert}. Browser trust must be configured separately.')
