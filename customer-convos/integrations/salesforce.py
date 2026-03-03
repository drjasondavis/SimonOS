from simple_salesforce import Salesforce
import config

_client = None


def get_client() -> Salesforce:
    global _client
    if _client is None:
        _client = Salesforce(
            username=config.SALESFORCE_USERNAME,
            password=config.SALESFORCE_PASSWORD,
            security_token=config.SALESFORCE_SECURITY_TOKEN,
            domain=config.SALESFORCE_DOMAIN,
        )
    return _client


def find_account_by_domain(domain: str) -> dict | None:
    """Look up a Salesforce Account by website domain."""
    sf = get_client()
    result = sf.query(
        f"SELECT Id, Name, Website FROM Account WHERE Website LIKE '%{domain}%' LIMIT 1"
    )
    records = result.get("records", [])
    return records[0] if records else None
