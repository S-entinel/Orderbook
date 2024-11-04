import math
from dataclasses import dataclass
from ordertypes import OrderType, Side

@dataclass
class LevelInfo:
    price: float
    quantity: int

@dataclass
class TradeInfo:
    order_id: int
    price: float
    quantity: int

@dataclass
class Trade:
    bid_trade: TradeInfo
    ask_trade: TradeInfo

class Order:
    def __init__(self, order_type: OrderType, order_id: int, side: Side, price: float, quantity: int):
        self.order_type = order_type
        self.order_id = order_id
        self.side = side
        self.price = price
        self.initial_quantity = quantity
        self.remaining_quantity = quantity

    @classmethod
    def create_market_order(cls, order_id: int, side: Side, quantity: int):
        return cls(OrderType.MARKET, order_id, side, math.nan, quantity)

    def get_filled_quantity(self) -> int:
        return self.initial_quantity - self.remaining_quantity

    def is_filled(self) -> bool:
        return self.remaining_quantity == 0

    def fill(self, quantity: int):
        if quantity > self.remaining_quantity:
            raise ValueError(f"Order ({self.order_id}) cannot be filled for more than its remaining quantity.")
        self.remaining_quantity -= quantity

    def to_good_till_cancel(self, price: float):
        if self.order_type != OrderType.MARKET:
            raise ValueError(f"Order ({self.order_id}) cannot have its price adjusted, only market orders can.")
        self.price = price
        self.order_type = OrderType.GOOD_TILL_CANCEL

class OrderModify:
    def __init__(self, order_id: int, side: Side, price: float, quantity: int):
        self.order_id = order_id
        self.price = price
        self.side = side
        self.quantity = quantity

    def to_order(self, order_type: OrderType) -> Order:
        return Order(order_type, self.order_id, self.side, self.price, self.quantity)