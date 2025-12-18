from py_vapid import Vapid

vapid = Vapid()
keys = vapid.generate_keys()

print(f"VAPID_PRIVATE_KEY={keys.private_key}")
print(f"VAPID_PUBLIC_KEY={keys.public_key}")
