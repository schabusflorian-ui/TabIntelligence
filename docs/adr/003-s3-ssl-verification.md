# ADR-003: Enable SSL Verification for S3 Connections

## Status
Accepted

## Date
2026-02-24

## Context

### Problem
The S3/MinIO client had SSL certificate verification DISABLED:

```python
# DANGEROUS - Before
self.client = boto3.client(
    "s3",
    endpoint_url=endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
    verify=False,  # DISABLED - Allows MITM attacks
)
```

And the factory function hardcoded `verify_ssl=False`:

```python
# Before
return S3Client(
    endpoint=settings.s3_endpoint,
    access_key=settings.s3_access_key,
    secret_key=settings.s3_secret_key,
    bucket_name=settings.s3_bucket,
    verify_ssl=False  # Hardcoded insecure
)
```

### Security Risk: Man-in-the-Middle (MITM) Attacks

With `verify=False`, the S3 client:
- ❌ Does NOT verify the server's SSL certificate
- ❌ Cannot detect impersonation attacks
- ❌ Transmits credentials in potentially compromised connections
- ❌ Violates security best practices

**Attack Scenario**:
1. Attacker intercepts network traffic between API server and S3
2. Attacker presents fake certificate (normally rejected)
3. Client accepts fake certificate due to `verify=False`
4. Attacker reads/modifies uploaded files and steals S3 credentials

### Why Was It Disabled?

Local MinIO development environments often use self-signed certificates:
- Self-signed certs are rejected by default SSL verification
- Developers disabled verification to get MinIO working
- Insecure setting was accidentally deployed to production

## Decision

### Enable SSL Verification by Default

Make SSL verification the default, with opt-out only for local development:

1. **Add Configuration Setting**:
   ```python
   # src/core/config.py
   s3_verify_ssl: bool = Field(
       default=True,  # Secure by default
       description="Verify SSL certificates for S3 connections"
   )
   ```

2. **Update S3 Client**:
   ```python
   # src/storage/s3.py
   return S3Client(
       endpoint=settings.s3_endpoint,
       access_key=settings.s3_access_key,
       secret_key=settings.s3_secret_key,
       bucket_name=settings.s3_bucket,
       verify_ssl=settings.s3_verify_ssl  # Use configured value
   )
   ```

3. **Add Retry Configuration**:
   ```python
   # Configure retries with exponential backoff
   retry_config = Config(
       retries={
           'max_attempts': 3,
           'mode': 'adaptive'
       }
   )

   self.client = boto3.client(
       's3',
       endpoint_url=endpoint,
       aws_access_key_id=access_key,
       aws_secret_access_key=secret_key,
       verify=verify_ssl,
       config=retry_config  # Add resilience
   )
   ```

4. **Document in .env.example**:
   ```bash
   # .env.example
   S3_VERIFY_SSL=false  # Development only - MUST be true in production
   ```

## Implementation

### Files Changed

1. **src/core/config.py**:
   - Added `s3_verify_ssl: bool = Field(default=True)`
   - Added `s3_region: Optional[str] = Field(default="us-east-1")`

2. **src/storage/s3.py**:
   - Added `from botocore.config import Config` import
   - Added retry configuration to S3 client
   - Changed `verify_ssl=False` to `verify_ssl=settings.s3_verify_ssl`

3. **.env.example**:
   - Added `S3_VERIFY_SSL` documentation
   - Added security warning about production usage

### Configuration Examples

**Development (Local MinIO)**:
```bash
# .env
S3_ENDPOINT=http://localhost:9000
S3_VERIFY_SSL=false  # OK for local MinIO with self-signed cert
```

**Staging/Production (AWS S3 or production MinIO)**:
```bash
# .env
S3_ENDPOINT=https://s3.us-east-1.amazonaws.com
S3_VERIFY_SSL=true  # REQUIRED for production
```

## Consequences

### Positive
- ✅ **Protected Against MITM Attacks**: Server identity verified by SSL certificate
- ✅ **Follows Security Best Practices**: SSL verification is industry standard
- ✅ **Secure by Default**: New deployments are secure without configuration
- ✅ **Compliance**: Meets security audit requirements
- ✅ **Retry Logic**: Added exponential backoff for transient failures

### Negative
- ⚠️ **Requires Valid Certificates in Production**: Cannot use self-signed certs
- ⚠️ **Local Development Setup**: Developers must set S3_VERIFY_SSL=false
- ⚠️ **Certificate Management**: Must maintain valid SSL certificates

### Trade-offs
- **Security vs Development Convenience**: Developers must explicitly opt-out for local development
- **Default Secure vs Default Permissive**: Chose security over convenience

## Production Requirements

### AWS S3
- ✅ Already has valid SSL certificates
- ✅ No changes needed, works out of the box

### Self-Hosted MinIO
Must configure valid SSL certificates:

**Option A: Let's Encrypt (Recommended)**:
```bash
# Get free SSL certificate
certbot certonly --standalone -d minio.example.com

# Configure MinIO
export MINIO_OPTS="--certs-dir /etc/letsencrypt/live/minio.example.com"
minio server /data
```

**Option B: Corporate CA**:
```bash
# Use corporate certificate authority
cp corporate-ca.crt /etc/ssl/certs/
update-ca-certificates

# MinIO automatically uses system certificates
minio server /data
```

**Option C: Self-Signed (NOT RECOMMENDED for production)**:
```bash
# Only for internal testing environments
# NEVER use in production
S3_VERIFY_SSL=false
```

## Local Development

### MinIO with Self-Signed Certificate

```bash
# .env
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=financial-models
S3_VERIFY_SSL=false  # ONLY for local development
```

### Warning in README
Added section to README.md:

```markdown
## Local Development with MinIO

For local development with self-signed certificates:

\`\`\`bash
# .env
S3_VERIFY_SSL=false  # ONLY for local development
\`\`\`

**NEVER set S3_VERIFY_SSL=false in production**
This makes connections vulnerable to man-in-the-middle attacks.
```

## Alternatives Considered

### Option A: Keep SSL Verification Disabled
- **Rejected**: Unacceptable security risk
- MITM attacks could compromise credentials and data

### Option B: Allow Both HTTP and HTTPS
- **Rejected**: HTTP is never secure, even with verify=True
- Still vulnerable to downgrade attacks

### Option C: Separate Dev/Prod Configurations
- **Rejected**: Easy to accidentally deploy dev config to prod
- Secure-by-default is better

### Option D: Certificate Pinning
- **Considered for future**: Pin specific certificates for extra security
- Not implemented now due to complexity
- May add in Phase 2 security hardening

## Validation

### Verification Steps

1. ✅ SSL verification enabled in code:
   ```bash
   grep "verify=" src/storage/s3.py
   # Result: verify=settings.s3_verify_ssl (NOT verify=False)
   ```

2. ✅ Configuration defaults to secure:
   ```bash
   grep "s3_verify_ssl" src/core/config.py
   # Result: default=True
   ```

3. ✅ Documentation added:
   ```bash
   grep "S3_VERIFY_SSL" .env.example
   # Result: Found with security warning
   ```

4. ✅ Retry configuration added:
   ```bash
   grep "retry_config" src/storage/s3.py
   # Result: Found with adaptive retries
   ```

### Testing

**Test SSL verification works**:
```python
from src.core.config import get_settings
from src.storage.s3 import get_s3_client

# Production config (SSL enabled)
settings = get_settings()
assert settings.s3_verify_ssl == True

# Client should verify SSL
s3 = get_s3_client(settings)
assert s3.verify_ssl == True

# Should work with valid certificate
s3.ensure_bucket_exists()  # Success

# Should FAIL with self-signed cert (expected)
# This proves verification is working
```

**Test retry logic**:
```python
# Client should retry on transient failures
s3 = get_s3_client(settings)
# Retries up to 3 times with exponential backoff
```

## Security Considerations

### Defense in Depth
SSL verification is one layer:
- ✅ SSL verification (this ADR)
- ✅ Encrypted credentials in environment variables
- ✅ IAM roles with minimal permissions
- ✅ S3 bucket policies restricting access
- ✅ Network isolation (VPC/firewall rules)

### Credential Protection
Even with SSL verification, protect credentials:
- Never commit .env files to git
- Use AWS IAM roles when possible
- Rotate credentials regularly
- Monitor access logs

### Future Enhancements
- Certificate pinning for critical endpoints
- Mutual TLS (mTLS) for service-to-service auth
- Hardware security modules (HSM) for key storage

## Monitoring

Monitor SSL-related errors:
```python
# src/storage/s3.py
try:
    s3.upload_file(...)
except ClientError as e:
    if "SSL" in str(e) or "certificate" in str(e):
        logger.error(f"SSL verification failed: {e}")
        # Alert security team
```

Alert on:
- SSL certificate verification failures
- Certificate expiration approaching
- Unexpected certificate changes

## References

- OWASP: Transport Layer Protection Cheat Sheet
- AWS S3 Security Best Practices
- boto3 Documentation: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html
- MinIO TLS Configuration: https://min.io/docs/minio/linux/operations/network-encryption.html

## Compliance

This change helps meet:
- SOC 2 Type II: Encryption in transit
- PCI DSS 4.1: Encrypted transmission of cardholder data
- GDPR Art. 32: Security of processing
- HIPAA: Encryption standards (if applicable)

## Rollback Plan

If SSL verification causes issues:

1. **Emergency rollback**:
   ```bash
   # .env (temporary only)
   S3_VERIFY_SSL=false
   ```

2. **Investigate root cause**:
   - Invalid/expired certificate?
   - Self-signed cert in production?
   - Network/firewall issue?

3. **Permanent fix**:
   - Install valid SSL certificate
   - Configure certificate authority
   - Fix network routing

**DO NOT leave S3_VERIFY_SSL=false in production**

## Approval

- Security Team: Approved
- DevOps Team: Approved (with documentation)
- Engineering Team: Approved
