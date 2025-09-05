import logging, random, string
from dataclasses import dataclass

@dataclass
class ADUser:
    SamAccountName: str
    DisplayName: str
    DistinguishedName: str
    Enabled: bool

async def search_candidates(query: str) -> list[ADUser]:
    # TODO: подключить pyad/ldap3/winrm
    demo = [
        ADUser("nustinova", "Устинова Наталья", "CN=Nat,OU=Users,DC=corp,DC=local", True),
        ADUser("nustinovam", "Устинова Марина", "CN=Marina,OU=Users,DC=corp,DC=local", True),
    ]
    return [u for u in demo if query.lower() in u.DisplayName.lower()]

async def reset_password(sam: str, length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    pwd = "".join(random.choice(chars) for _ in range(length))
    logging.info("Reset password for %s", sam)
    # TODO: реальная смена пароля
    return pwd

async def disable_user(sam: str):
    logging.info("Disable user %s", sam)
    # TODO: реальное отключение в AD
