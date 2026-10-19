"""Offline targeted regressions. All HTTP is mocked; no charges, sends, or refunds."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
from flask import Flask
import checkout_gate as cg
import order_fulfillment as of
import stripe_bridge as sb
import launch_config as lc

class LaunchPreparation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            'RAILWAY_VOLUME_MOUNT_PATH': self.tmp.name, 'STRIPE_WEBHOOK_SECRET': 'whsec_fixture',
            'STRIPE_CHECKOUT_KEY': 'rk_test_fixture', 'STRIPE_REFUND_KEY': 'rk_test_fixture',
            'STRIPE_AUTO_REFUND': '1', 'LEADS_PROVIDER': 'overture', 'FULFILLMENT_MAX_LEADS': '10',
            'FULFILLMENT_TEST_RECIPIENTS': 'founder@example.com', 'ORDER_WEBHOOK_SECRET': 'fixture',
            'ORDER_FULFILLMENT_ENABLED': '1',
        }, clear=True)
        self.env.start()
        self.http = patch('requests.post', side_effect=AssertionError('unexpected HTTP'))
        self.post = self.http.start()
        self.addCleanup(self.http.stop); self.addCleanup(self.env.stop); self.addCleanup(self.tmp.cleanup)
        of.init_db(); sb._tbl()
        app = Flask(__name__); app.register_blueprint(cg.bp2); app.register_blueprint(sb.bp)
        self.client = app.test_client()
        self.order = dict(product=cg.PRODUCT, business_type='plumber', city='Cheyenne', state='WY', quantity=10)

    def live(self):
        os.environ.update({k:'1' for k in lc.LIVE_FLAGS})
        os.environ.update(STRIPE_CHECKOUT_KEY='rk_live_fixture', STRIPE_REFUND_KEY='rk_live_fixture',
            RESEND_API_KEY='fixture', RESEND_FROM='Lyra Sha AI <ingrid@lyrashaai.com>',
            CHECKOUT_SUCCESS_URL='https://www.lyrashaai.com/leads/success',
            CHECKOUT_CANCEL_URL='https://www.lyrashaai.com/leads/cancel')

    def event(self, **session):
        return dict(id='evt_fixture', type='checkout.session.completed', livemode=False, data={'object':{
            'id':'cs_fixture', 'payment_intent':'pi_fixture', 'payment_status':'paid', 'amount_total':2900,
            'currency':'usd', 'customer_email':'buyer@example.com',
            'metadata':dict(product=cg.PRODUCT, business_type='plumber', city='Cheyenne', state='WY', quantity='10'), **session}})

    def send(self, ev, valid=True):
        raw=json.dumps(ev).encode(); ts=int(time.time())
        sig=hmac.new(b'whsec_fixture',str(ts).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return self.client.post('/stripe/webhook',data=raw,headers={'Stripe-Signature':f't={ts},v1={sig if valid else "bad"}'})

    def seed(self, status='SHORTFALL', note='', attempts=0):
        with of.db() as c:
            c.execute('INSERT INTO orders(order_id,status,attempts,last_error) VALUES(?,?,?,?)',('STRIPE-cs_fixture',status,attempts,'shortfall'))
            c.execute('INSERT INTO stripe_orders VALUES(?,?,?,?,?,?,?)',('STRIPE-cs_fixture','cs_fixture','pi_fixture',2900,0,1,note))

    def test_live_checkout_off_by_default(self):
        os.environ['STRIPE_CHECKOUT_KEY']='rk_live_fixture'
        with patch.object(cg,'qualified_count',return_value=10):
            self.assertEqual(self.client.post('/checkout/session',json=self.order).status_code,403)
        self.post.assert_not_called()

    def test_each_live_prerequisite_is_required(self):
        self.live(); self.assertEqual(lc.live_blockers(),[])
        for name in (*lc.LIVE_FLAGS,'STRIPE_AUTO_REFUND','STRIPE_REFUND_KEY','STRIPE_CHECKOUT_KEY','RESEND_API_KEY','STRIPE_WEBHOOK_SECRET','RAILWAY_VOLUME_MOUNT_PATH'):
            with self.subTest(name=name), patch.dict(os.environ,{name:''}):
                self.assertTrue(lc.live_blockers())
                with self.assertRaises(RuntimeError): lc.validate_startup()

    def test_live_checkout_exact_price_and_spanish(self):
        self.live(); os.environ['CHECKOUT_PRICE_CENTS']='1'
        self.post.side_effect=None; self.post.return_value=Mock(status_code=200,json=lambda:{'id':'cs_live_fixture','url':'https://checkout.stripe.com/fixture'})
        with patch.object(cg,'qualified_count',return_value=10):
            r=self.client.post('/checkout/session',json={**self.order,'locale':'es'})
        self.assertEqual(r.status_code,200)
        params=self.post.call_args.kwargs['data']
        self.assertEqual(params['locale'],'es'); self.assertEqual(params['line_items[0][price_data][unit_amount]'],'2900')
        self.assertNotIn('(TEST)',params['line_items[0][price_data][product_data][name]'])

    def test_unavailable_and_short_inventory_never_calls_stripe(self):
        with patch.object(cg,'qualified_count',return_value=9):
            self.assertEqual(self.client.post('/checkout/session',json=self.order).status_code,409)
            self.assertEqual(self.client.post('/checkout/session',json={**self.order,'business_type':'hvac'}).status_code,422)
            self.assertEqual(self.client.post('/checkout/session',json={**self.order,'price_cents':1}).status_code,422)
        self.post.assert_not_called()

    def test_bad_signature_and_live_disabled(self):
        self.assertEqual(self.send(self.event(),False).status_code,400)
        ev=self.event(); ev['livemode']=True
        self.assertEqual(self.send(ev).get_json()['ignored'],'live-mode events disabled')

    def test_duplicate_session_and_event_no_second_worker(self):
        with patch.object(sb.threading,'Thread') as thread:
            self.assertEqual(self.send(self.event()).status_code,200)
            self.assertTrue(self.send(self.event()).get_json()['duplicate'])
            ev=self.event(); ev['id']='evt_second'
            self.assertTrue(self.send(ev).get_json()['duplicate'])
            self.assertEqual(thread.call_count,1)
        with of.db() as c: self.assertEqual(c.execute('SELECT count(*) FROM orders').fetchone()[0],1)

    def test_test_event_stays_founder_only_after_live_activation(self):
        self.live()
        with patch.object(sb.threading,'Thread'):
            self.assertEqual(self.send(self.event()).status_code,200)
        with of.db() as c:
            row=c.execute('SELECT customer_email,is_test FROM orders').fetchone()
        self.assertEqual(tuple(row),('founder@example.com',1))

    def test_invalid_metadata_retry_does_not_burn_event(self):
        ev=self.event(metadata={})
        self.assertEqual(self.send(ev).status_code,400)
        with patch.object(sb.threading,'Thread'):
            self.assertFalse(self.send(self.event()).get_json()['duplicate'])

    def test_insert_failure_rolls_back_order_and_event(self):
        with of.db() as c:
            c.execute("CREATE TRIGGER fail_mapping BEFORE INSERT ON stripe_orders BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        self.assertEqual(self.send(self.event()).status_code,503)
        with of.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM orders').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM stripe_events').fetchone()[0],0)
            c.execute('DROP TRIGGER fail_mapping')
        with patch.object(sb.threading,'Thread'):
            self.assertFalse(self.send(self.event()).get_json()['duplicate'])

    def test_live_paid_offer_mismatch_rejected(self):
        self.live()
        for changes in ({'amount_total':1},{'currency':'eur'},{'metadata':{}}):
            ev=self.event(**changes); ev['livemode']=True
            self.assertEqual(self.send(ev).status_code,400)
        self.post.assert_not_called()

    def test_refund_mode_mismatch_and_live_gate(self):
        self.assertFalse(sb.auto_refund('x','pi_fixture',True)[0])
        os.environ['STRIPE_REFUND_KEY']='rk_live_fixture'
        self.assertFalse(sb.auto_refund('x','pi_fixture',False)[0])
        self.assertFalse(sb.auto_refund('x','pi_fixture',True)[0]); self.post.assert_not_called()

    def test_pending_refund_remains_due(self):
        self.seed()
        self.post.side_effect=None; self.post.return_value=Mock(ok=True,json=lambda:{'id':'re_fixture','status':'pending','amount':2900})
        with patch.object(of,'process_order'),patch.object(sb,'alert'):
            sb._run('STRIPE-cs_fixture')
        with of.db() as c: self.assertEqual(c.execute('SELECT refund_due FROM stripe_orders').fetchone()[0],1)
        self.assertEqual(self.post.call_args.kwargs['headers']['Idempotency-Key'],'refund-STRIPE-cs_fixture')

    def test_shortfall_full_refund_never_partial_delivery(self):
        self.seed()
        self.post.side_effect=None; self.post.return_value=Mock(ok=True,json=lambda:{'id':'re_fixture','status':'succeeded','amount':2900})
        with patch.object(of,'process_order'),patch.object(sb,'alert'):
            sb._run('STRIPE-cs_fixture'); sb._run('STRIPE-cs_fixture')
        self.assertEqual(self.post.call_count,1)
        self.assertNotIn('amount',self.post.call_args.kwargs['data']) # Stripe full refund
        with of.db() as c: self.assertEqual(c.execute('SELECT refund_due FROM stripe_orders').fetchone()[0],0)

    def test_restart_recovers_exhausted_and_shortfall_through_bridge(self):
        self.seed(status='FAILED',attempts=3)
        with patch.object(sb.threading,'Thread') as thread:
            self.assertEqual(sb.resume_unfinished(),['STRIPE-cs_fixture'])
            self.assertIs(thread.call_args.kwargs['target'],sb._run)

    def test_refunded_order_never_restarts_generic_delivery(self):
        self.seed(status='FAILED',note='AUTO-REFUNDED fixture')
        with patch.object(sb.threading,'Thread') as thread:
            app=Flask('recovery'); of.register(app)
            thread.assert_not_called()

if __name__=='__main__': unittest.main(verbosity=2)
