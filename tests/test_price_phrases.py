import unittest
from liveclip.policy import PROMOTION_PATTERN

class PriceTests(unittest.TestCase):
    def test_order_pressure_and_live_size_interactions_are_filtered(self):
        for text in ['宝贝们放放心心拍，定定心心买','可以把链接号加身高体重都给我，我这边给你们做推荐']:
            with self.subTest(text=text):self.assertIsNotNone(PROMOTION_PATTERN.search(text))
    def test_colloquial_expiring_prices_are_filtered(self):
        for text in ['你凑完单就是100多块钱','你现在买个卫衣要一两百块钱','这个只要一百多元']:
            with self.subTest(text=text):self.assertIsNotNone(PROMOTION_PATTERN.search(text))
    def test_product_number_is_not_price(self):
        self.assertIsNone(PROMOTION_PATTERN.search('40号裤子垂感好，两侧有口袋'))
    def test_direct_purchase_call_is_filtered_but_sizing_is_kept(self):
        self.assertIsNotNone(PROMOTION_PATTERN.search('我身上这件卡码得拍大哦，你如果是喜欢的话可以直接买。然后它里面是带一点这种绒的'))
        self.assertIsNotNone(PROMOTION_PATTERN.search('能买的一号链接，今天买一单自己去感受一下，反正这个品质真的没话说'))
        self.assertIsNone(PROMOTION_PATTERN.search('这件卡码建议拍大一码，内里带绒，可以当内搭也可以外穿'))

if __name__=='__main__':unittest.main()
