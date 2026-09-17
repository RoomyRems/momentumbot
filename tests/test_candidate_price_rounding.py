from fractions import Fraction
import unittest

import pandas as pd

from momentumbot.research import candidate_price_rounding as m


class PriceRoundingTests(unittest.TestCase):
    def frame(self, values):
        return pd.DataFrame({'close':values},index=pd.date_range('2026-03-04T09:00Z',periods=len(values),freq='min'))

    def case(self, raw, split, raw_high=4, split_high=60):
        return m.explain_case(self.frame(raw),self.frame(split),raw_daily_high=raw_high,split_daily_high=split_high)

    def test_exact_factor_preserves_subcent_prices(self):
        v=self.case([1.0001,2.0001],[1.0001,2.0001],raw_high=4.0001,split_high=4.0001)
        self.assertEqual(v['status'],'exact_constant_factor')
        self.assertEqual(v['factor'],{'numerator':1,'denominator':1})
        self.assertFalse(v['runtime_normalization_authorized'])

    def test_cent_model_explains_adjusted_subcent_raw_without_tolerance(self):
        v=self.case([1.7063,1.5008],[25.59,22.51])
        self.assertEqual(v['status'],'compatible_nearest_cent_rounding')
        self.assertFalse(v['vendor_rounding_documented']);self.assertFalse(v['daily_minute_share_basis_verified'])
        lo=Fraction(v['interval_lower']['numerator'],v['interval_lower']['denominator'])
        hi=Fraction(v['interval_upper']['numerator'],v['interval_upper']['denominator'])
        self.assertLessEqual(lo,15);self.assertGreaterEqual(hi,15)

    def test_rounded_daily_high_does_not_become_exact_factor(self):
        v=self.case([1.36,1.46],[9.52,10.22],raw_high=1.939,split_high=13.57)
        self.assertEqual(v['status'],'compatible_nearest_cent_rounding')
        lo=Fraction(v['interval_lower']['numerator'],v['interval_lower']['denominator'])
        hi=Fraction(v['interval_upper']['numerator'],v['interval_upper']['denominator'])
        self.assertLessEqual(lo,7);self.assertGreaterEqual(hi,7)

    def test_inconsistent_factors_are_not_hidden_by_rounding(self):
        self.assertEqual(self.case([2,3],[30,46])['status'],'incompatible_constant_factor')
        self.assertEqual(self.case([2,3],[30,45],raw_high=4,split_high=80)['status'],'incompatible_constant_factor')

    def test_unknown_adjusted_precision_is_explicit(self):
        self.assertEqual(self.case([2,3],[30.001,45])['status'],'not_on_cent_grid')

    def test_half_cent_boundary_is_exact_and_ties_are_unproven(self):
        lo,hi=m.nearest_cent_factor_interval(1,1)
        self.assertEqual(lo,Fraction(199,200));self.assertEqual(hi,Fraction(201,200))
        with self.assertRaises(ValueError):m.nearest_cent_factor_interval(1,1.0001)

    def test_observed_precision_is_separate_and_does_not_relax_cent_model(self):
        kwargs=dict(raw_daily_high=1.939,split_daily_high=13.57)
        raw,split=self.frame([1.425,1.4002]),self.frame([9.975,9.801])
        self.assertEqual(m.explain_case(raw,split,**kwargs)['status'],'not_on_cent_grid')
        v=m.explain_case(raw,split,model='observed_precision',**kwargs)
        self.assertEqual(v['status'],'compatible_observed_precision')
        self.assertFalse(v['runtime_normalization_authorized'])
        split.iloc[1,0]=9.805
        self.assertEqual(m.explain_case(raw,split,model='observed_precision',**kwargs)['status'],'incompatible_constant_factor')

    def test_observed_precision_grid_and_ten_boundary_are_fixed(self):
        for adjusted,expected in [(9.999,'compatible_observed_precision'),(10.001,'not_on_model_grid')]:
            v=m.explain_case(self.frame([1]),self.frame([adjusted]),raw_daily_high=2,split_daily_high=20,model='observed_precision')
            self.assertEqual(v['status'],expected)
        with self.assertRaises(ValueError):m.explain_case(self.frame([1]),self.frame([1]),raw_daily_high=2,split_daily_high=2,model='fit_to_data')

    def test_empty_missing_and_invalid_are_not_success(self):
        self.assertEqual(self.case([],[])['status'],'empty_pair')
        self.assertEqual(self.case([1],[])['status'],'timestamp_mismatch')
        for x in [0,-1,float('nan'),float('inf'),True]:
            with self.subTest(x=x),self.assertRaises(ValueError):self.case([x],[1])


if __name__=='__main__':unittest.main()
