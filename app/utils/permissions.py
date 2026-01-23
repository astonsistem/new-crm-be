from enum import Enum
from typing import List

class Permission(str, Enum):
    # Customer permissions
    CREATE_CUSTOMER = "create_customer"
    VIEW_CUSTOMER = "view_customer"
    EDIT_CUSTOMER = "edit_customer"
    DELETE_CUSTOMER = "delete_customer"
    
    # MOU permissions
    CREATE_MOU = "create_mou"
    VIEW_MOU = "view_mou"
    EDIT_MOU = "edit_mou"
    DELETE_MOU = "delete_mou"
    
    