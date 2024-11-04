import unittest
from orderbook import Orderbook
from order import Order, OrderModify, Trade, TradeInfo
from ordertypes import OrderType, Side

class TestOrderbook(unittest.TestCase):
    def setUp(self):
        self.orderbook = Orderbook()

    def tearDown(self):
        if hasattr(self, 'orderbook'):
            self.orderbook.cleanup()
            self.orderbook = None

    def test_add_simple_limit_orders(self):
        """Test adding basic limit orders without matching"""
        # Add a buy order
        buy_order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=1,
            side=Side.BUY,
            price=100.0,
            quantity=10
        )
        trades = self.orderbook.add_order(buy_order)
        self.assertEqual(len(trades), 0)
        self.assertEqual(self.orderbook.size(), 1)

        # Add a sell order at higher price (should not match)
        sell_order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=2,
            side=Side.SELL,
            price=101.0,
            quantity=10
        )
        trades = self.orderbook.add_order(sell_order)
        self.assertEqual(len(trades), 0)
        self.assertEqual(self.orderbook.size(), 2)

        # Verify orderbook state
        bid_infos, ask_infos = self.orderbook.get_order_infos()
        self.assertEqual(len(bid_infos), 1)
        self.assertEqual(len(ask_infos), 1)
        self.assertEqual(bid_infos[0].price, 100.0)
        self.assertEqual(ask_infos[0].price, 101.0)

    def test_matching_orders(self):
        """Test matching orders at same price"""
        # Add a buy order
        buy_order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=1,
            side=Side.BUY,
            price=100.0,
            quantity=10
        )
        trades = self.orderbook.add_order(buy_order)
        self.assertEqual(len(trades), 0)

        # Add matching sell order
        sell_order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=2,
            side=Side.SELL,
            price=100.0,
            quantity=5
        )
        trades = self.orderbook.add_order(sell_order)
        
        # Verify trade occurred
        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade.bid_trade.order_id, 1)
        self.assertEqual(trade.ask_trade.order_id, 2)
        self.assertEqual(trade.bid_trade.quantity, 5)
        self.assertEqual(trade.ask_trade.quantity, 5)

        # Verify remaining quantity
        self.assertEqual(self.orderbook.size(), 1)  # Only buy order remains
        bid_infos, ask_infos = self.orderbook.get_order_infos()
        self.assertEqual(len(bid_infos), 1)
        self.assertEqual(len(ask_infos), 0)
        self.assertEqual(bid_infos[0].quantity, 5)

    def test_market_order(self):
        """Test market order execution"""
        # Add a sell limit order first
        sell_order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=1,
            side=Side.SELL,
            price=100.0,
            quantity=10
        )
        self.orderbook.add_order(sell_order)

        # Add a market buy order
        market_order = Order.create_market_order(
            order_id=2,
            side=Side.BUY,
            quantity=5
        )
        trades = self.orderbook.add_order(market_order)

        # Verify trade occurred
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].bid_trade.quantity, 5)
        self.assertEqual(trades[0].ask_trade.quantity, 5)

        # Verify remaining sell order
        bid_infos, ask_infos = self.orderbook.get_order_infos()
        self.assertEqual(len(ask_infos), 1)
        self.assertEqual(ask_infos[0].quantity, 5)

    def test_fill_or_kill_order(self):
        """Test fill-or-kill order behavior"""
        # Add sell orders
        sell_order1 = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=1,
            side=Side.SELL,
            price=100.0,
            quantity=5
        )
        self.orderbook.add_order(sell_order1)

        # Try to execute fill-or-kill for larger quantity
        fok_order = Order(
            order_type=OrderType.FILL_OR_KILL,
            order_id=2,
            side=Side.BUY,
            price=100.0,
            quantity=10
        )
        trades = self.orderbook.add_order(fok_order)
        
        # Verify order was killed
        self.assertEqual(len(trades), 0)
        self.assertEqual(self.orderbook.size(), 1)

        # Try fill-or-kill with executable quantity
        fok_order2 = Order(
            order_type=OrderType.FILL_OR_KILL,
            order_id=3,
            side=Side.BUY,
            price=100.0,
            quantity=5
        )
        trades = self.orderbook.add_order(fok_order2)
        
        # Verify full execution
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].bid_trade.quantity, 5)
        self.assertEqual(self.orderbook.size(), 0)

    def test_fill_and_kill_order(self):
        """Test fill-and-kill order behavior"""
        # Add sell orders at different prices
        sell_order1 = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=1,
            side=Side.SELL,
            price=100.0,
            quantity=5
        )
        sell_order2 = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=2,
            side=Side.SELL,
            price=101.0,
            quantity=5
        )
        self.orderbook.add_order(sell_order1)
        self.orderbook.add_order(sell_order2)

        # Add fill-and-kill buy order
        fak_order = Order(
            order_type=OrderType.FILL_AND_KILL,
            order_id=3,
            side=Side.BUY,
            price=101.0,
            quantity=7
        )
        trades = self.orderbook.add_order(fak_order)

        # Verify partial execution and killing of remaining quantity
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].bid_trade.quantity, 5)
        self.assertEqual(self.orderbook.size(), 1)  # Only second sell order remains

    def test_modify_order(self):
        """Test order modification"""
        # Add original order
        original_order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=1,
            side=Side.BUY,
            price=100.0,
            quantity=10
        )
        self.orderbook.add_order(original_order)

        # Modify order
        modify = OrderModify(
            order_id=1,
            side=Side.BUY,
            price=101.0,
            quantity=15
        )
        self.orderbook.modify_order(modify)

        # Verify modification
        bid_infos, ask_infos = self.orderbook.get_order_infos()
        self.assertEqual(len(bid_infos), 1)
        self.assertEqual(bid_infos[0].price, 101.0)
        self.assertEqual(bid_infos[0].quantity, 15)

    def test_cancel_order(self):
        """Test order cancellation"""
        # Add order
        order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=1,
            side=Side.BUY,
            price=100.0,
            quantity=10
        )
        self.orderbook.add_order(order)
        self.assertEqual(self.orderbook.size(), 1)

        # Cancel order
        self.orderbook.cancel_order(1)
        self.assertEqual(self.orderbook.size(), 0)
        bid_infos, ask_infos = self.orderbook.get_order_infos()
        self.assertEqual(len(bid_infos), 0)

    def test_multiple_price_levels(self):
        """Test handling of multiple price levels"""
        # Add several buy orders at different prices
        buy_orders = [
            Order(OrderType.GOOD_TILL_CANCEL, 1, Side.BUY, 100.0, 10),
            Order(OrderType.GOOD_TILL_CANCEL, 2, Side.BUY, 99.0, 20),
            Order(OrderType.GOOD_TILL_CANCEL, 3, Side.BUY, 98.0, 30),
        ]
        for order in buy_orders:
            self.orderbook.add_order(order)

        # Add sell order that matches highest bid
        sell_order = Order(
            order_type=OrderType.GOOD_TILL_CANCEL,
            order_id=4,
            side=Side.SELL,
            price=100.0,
            quantity=5
        )
        trades = self.orderbook.add_order(sell_order)

        # Verify trade at best price
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].bid_trade.price, 100.0)
        self.assertEqual(trades[0].bid_trade.quantity, 5)

        # Verify remaining orders
        bid_infos, ask_infos = self.orderbook.get_order_infos()
        self.assertEqual(len(bid_infos), 3)
        self.assertEqual(bid_infos[0].quantity, 5)  # Partially filled at 100.0
        self.assertEqual(bid_infos[1].quantity, 20)  # Full quantity at 99.0
        self.assertEqual(bid_infos[2].quantity, 30)  # Full quantity at 98.0

    def test_good_for_day_orders(self):
        """Test good-for-day orders"""
        # Add a good-for-day order
        gfd_order = Order(
            order_type=OrderType.GOOD_FOR_DAY,
            order_id=1,
            side=Side.BUY,
            price=100.0,
            quantity=10
        )
        self.orderbook.add_order(gfd_order)
        self.assertEqual(self.orderbook.size(), 1)

        # Note: We can't easily test the automatic cancellation at market close
        # in a unit test, but we can verify the order is added correctly

if __name__ == '__main__':
    unittest.main()