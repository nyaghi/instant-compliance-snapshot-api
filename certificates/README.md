# Florida certificate-chain recovery

`godaddy-r1-cross-g2.pem` is GoDaddy's public **GoDaddy TLS Root CA - R1 to G2 Cross Certificate**:
https://certs.godaddy.com/repository/gd_tls_root-r1-cross-g2.crt.pem

SHA-256 (DER): `7BCB0F2F2D1031A6AF8D61BAA835D2835A3B8BCC26D94A3B048B1655FB81298C`.

On September 24, 2026, csapp.fdacs.gov presented its September 18 leaf certificate and the OV R1v1 issuing intermediate, but omitted this cross certificate. Live staging failed with `ERR_CERT_AUTHORITY_INVALID`. Supplying the missing chain member made the same registry accessible with hostname and certificate verification enabled.

The master backend uses this asset only after a Florida browser authority failure, only for HTTPS requests to csapp.fdacs.gov, and within the original lookup deadline. It is added to a private SSL context as a chain member. Partial-chain trust is disabled, so verification must still terminate at an existing system root. It is not installed into the OS or browser trust store. The browser's existing form interaction, candidate matching and classification remain in use. Recovery routes are removed when the lookup finishes.

Do not replace this with `verify=False`, `ignore_https_errors`, a leaf-certificate exception, or a new trusted root. If the state repairs its chain, the normal browser path succeeds and the recovery is unused. Unknown, expired or wrong-host certificates must continue to fail conservatively. This is a public CA artifact, not an organization-specific exception or secret.
