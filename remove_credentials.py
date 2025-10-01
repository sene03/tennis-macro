import keyring
from config import SERVICE_NAME

# Define the service name and username of the credentials to be deleted
service_name = SERVICE_NAME
stored = ["user_id", "user_pw"]

for s in stored:
    try:
        # Attempt to delete the password
        keyring.delete_password(service_name, s)
        print(f"Credentials for service '{service_name}' and {s} deleted successfully.")
    except keyring.errors.PasswordDeleteError:
        print(f"No credentials found for service '{service_name}' and {s} to delete.")
    except Exception as e:
        print(f"An error occurred while deleting credentials: {e}")

    # Verify deletion by attempting to retrieve the password (it should return None)
    deleted_password = keyring.get_password(service_name, s)
    if deleted_password is None:
        print("Password retrieval after deletion confirms it's gone.")
    else:
        print("Password still exists after attempted deletion.")