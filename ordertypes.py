from enum import Enum, auto

class OrderType(Enum):
    GOOD_TILL_CANCEL = auto()
    FILL_AND_KILL = auto()
    FILL_OR_KILL = auto()
    GOOD_FOR_DAY = auto()
    MARKET = auto()

class Side(Enum):
    BUY = auto()
    SELL = auto()