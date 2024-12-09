import random
import string
def generate_class_code():
    """Generate a random 8-character alphanumeric code for the class."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))