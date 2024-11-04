from typing import Dict, List, Tuple
import threading
from datetime import datetime, timedelta
from collections import defaultdict
from ordertypes import OrderType, Side
from order import Order, OrderModify, Trade, TradeInfo, LevelInfo


class Orderbook:
    def __init__(self):
        self.data: Dict[float, Dict[str, int]] = defaultdict(lambda: {'quantity': 0, 'count': 0})
        self.bids: Dict[float, List[Order]] = {}  # Price -> Orders (sorted high to low)
        self.asks: Dict[float, List[Order]] = {}  # Price -> Orders (sorted low to high)
        self.orders: Dict[int, Tuple[Order, List[Order]]] = {}  # OrderId -> (Order, Reference to containing list)
        self.lock = threading.Lock()
        self.shutdown = False
        self.shutdown_event = threading.Event()
        # Make the thread a daemon thread
        self.prune_thread = threading.Thread(target=self._prune_good_for_day_orders, daemon=True)
        self.prune_thread.start()

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        if not self.shutdown:
            self.shutdown = True
            self.shutdown_event.set()
            if self.prune_thread.is_alive():
                try:
                    self.prune_thread.join(timeout=1.0)  # Add timeout to prevent hanging
                except RuntimeError:
                    pass  # Thread already stopped

    def _prune_good_for_day_orders(self):
        while not self.shutdown:
            try:
                now = datetime.now()
                next_run = now.replace(hour=16, minute=0, second=0, microsecond=0)
                if now.hour >= 16:
                    next_run += timedelta(days=1)
                
                wait_seconds = (next_run - now).total_seconds()
                # Use shorter timeout intervals to check shutdown more frequently
                if self.shutdown_event.wait(timeout=min(wait_seconds, 1.0)):
                    return

                if self.shutdown:
                    return

                order_ids = []
                with self.lock:
                    for order_id, (order, _) in self.orders.items():
                        if order.order_type == OrderType.GOOD_FOR_DAY:
                            order_ids.append(order_id)
                
                for order_id in order_ids:
                    self.cancel_order(order_id)
            except Exception:
                if not self.shutdown:
                    raise

    def _update_level_data(self, price: float, quantity: int, is_add: bool, is_match: bool = False):
        if is_add:
            self.data[price]['count'] += 1
            self.data[price]['quantity'] += quantity
        elif is_match:
            self.data[price]['quantity'] -= quantity
        else:  # remove
            self.data[price]['count'] -= 1
            self.data[price]['quantity'] -= quantity

        if self.data[price]['count'] == 0:
            del self.data[price]

    def _can_match(self, side: Side, price: float) -> bool:
        if side == Side.BUY:
            return bool(self.asks) and price >= min(self.asks.keys())
        else:
            return bool(self.bids) and price <= max(self.bids.keys())

    def _can_fully_fill(self, side: Side, price: float, quantity: int) -> bool:
        if not self._can_match(side, price):
            return False

        remaining_quantity = quantity
        relevant_prices = sorted(self.data.keys(), reverse=(side == Side.BUY))
        
        for level_price in relevant_prices:
            if (side == Side.BUY and level_price > price) or \
               (side == Side.SELL and level_price < price):
                continue

            level_quantity = self.data[level_price]['quantity']
            if remaining_quantity <= level_quantity:
                return True
            remaining_quantity -= level_quantity

        return False

    def _match_orders(self) -> List[Trade]:
        trades = []
        
        while self.bids and self.asks:
            best_bid_price = max(self.bids.keys())
            best_ask_price = min(self.asks.keys())
            
            if best_bid_price < best_ask_price:
                break

            while self.bids[best_bid_price] and self.asks[best_ask_price]:
                bid = self.bids[best_bid_price][0]
                ask = self.asks[best_ask_price][0]
                
                match_quantity = min(bid.remaining_quantity, ask.remaining_quantity)
                
                bid.fill(match_quantity)
                ask.fill(match_quantity)
                
                trades.append(Trade(
                    TradeInfo(bid.order_id, bid.price, match_quantity),
                    TradeInfo(ask.order_id, ask.price, match_quantity)
                ))
                
                self._update_level_data(bid.price, match_quantity, False, True)
                self._update_level_data(ask.price, match_quantity, False, True)
                
                # For fill-and-kill orders, stop after first match
                if (bid.order_type == OrderType.FILL_AND_KILL or 
                    ask.order_type == OrderType.FILL_AND_KILL):
                    if not bid.is_filled():
                        self.cancel_order(bid.order_id)
                    if not ask.is_filled():
                        self.cancel_order(ask.order_id)
                    return trades
                
                if bid.is_filled():
                    self.bids[best_bid_price].pop(0)
                    del self.orders[bid.order_id]
                
                if ask.is_filled():
                    self.asks[best_ask_price].pop(0)
                    del self.orders[ask.order_id]
                
                if not self.bids[best_bid_price]:
                    del self.bids[best_bid_price]
                    break
                    
                if not self.asks[best_ask_price]:
                    del self.asks[best_ask_price]
                    break

        return trades

    def add_order(self, order: Order) -> List[Trade]:
        with self.lock:
            if order.order_id in self.orders:
                return []

            if order.order_type == OrderType.MARKET:
                if order.side == Side.BUY and self.asks:
                    worst_ask = max(self.asks.keys())
                    order.to_good_till_cancel(worst_ask)
                elif order.side == Side.SELL and self.bids:
                    worst_bid = min(self.bids.keys())
                    order.to_good_till_cancel(worst_bid)
                else:
                    return []

            if order.order_type == OrderType.FILL_AND_KILL and \
               not self._can_match(order.side, order.price):
                return []

            if order.order_type == OrderType.FILL_OR_KILL and \
               not self._can_fully_fill(order.side, order.price, order.initial_quantity):
                return []

            orders_dict = self.bids if order.side == Side.BUY else self.asks
            if order.price not in orders_dict:
                orders_dict[order.price] = []
            
            orders_dict[order.price].append(order)
            self.orders[order.order_id] = (order, orders_dict[order.price])
            self._update_level_data(order.price, order.initial_quantity, True)
            
            return self._match_orders()

    def cancel_order(self, order_id: int):
        with self.lock:
            if order_id not in self.orders:
                return

            order, order_list = self.orders[order_id]
            del self.orders[order_id]
            
            order_list.remove(order)
            orders_dict = self.bids if order.side == Side.BUY else self.asks
            
            if not order_list:
                del orders_dict[order.price]
            
            self._update_level_data(order.price, order.remaining_quantity, False)

    def modify_order(self, modify: OrderModify) -> List[Trade]:
        with self.lock:
            if modify.order_id not in self.orders:
                return []
            
            original_order = self.orders[modify.order_id][0]
            order_type = original_order.order_type
            
            self.cancel_order(modify.order_id)
            return self.add_order(modify.to_order(order_type))

    def size(self) -> int:
        with self.lock:
            return len(self.orders)

    def get_order_infos(self) -> Tuple[List[LevelInfo], List[LevelInfo]]:
        with self.lock:
            bid_infos = []
            ask_infos = []
            
            for price, orders in self.bids.items():
                quantity = sum(order.remaining_quantity for order in orders)
                bid_infos.append(LevelInfo(price, quantity))
            
            for price, orders in self.asks.items():
                quantity = sum(order.remaining_quantity for order in orders)
                ask_infos.append(LevelInfo(price, quantity))
            
            return bid_infos, ask_infos