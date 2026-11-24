import unittest
from nv_community_preview_entrypoint import approved_clients

class GateTests(unittest.TestCase):
    def setUp(self):
        self.p='813874968486490'; self.q='565654433307015'
        self.config={'facebook_clients':[{'page_id':self.p},{'page_id':self.q},{'page_id':'other'}]}
        self.controls={'accounts':{self.p:{'paused':False,'founder_public_replies_approved':True},self.q:{'paused':True}}}
    def test_only_approved_page(self):
        self.assertEqual(approved_clients(self.config,self.controls,[self.p])['facebook_clients'],[{'page_id':self.p}])
    def test_empty_denied(self):
        with self.assertRaises(ValueError): approved_clients(self.config,self.controls,[])
    def test_outside_pilot_denied(self):
        with self.assertRaises(ValueError): approved_clients(self.config,self.controls,['other'])
    def test_paused_denied(self):
        with self.assertRaises(ValueError): approved_clients(self.config,self.controls,[self.q])
    def test_missing_approval_denied(self):
        self.controls['accounts'][self.p]['founder_public_replies_approved']=False
        with self.assertRaises(ValueError): approved_clients(self.config,self.controls,[self.p])
    def test_missing_credentials_denied(self):
        with self.assertRaises(ValueError): approved_clients({'facebook_clients':[]},self.controls,[self.p])
if __name__=='__main__': unittest.main()
