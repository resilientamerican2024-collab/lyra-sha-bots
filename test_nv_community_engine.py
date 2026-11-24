import unittest
from datetime import datetime, timezone, timedelta
from nv_community_engine import *

class CommunityTests(unittest.TestCase):
    def test_all_municipalities(self):
        self.assertEqual(78, len(MUNICIPALITIES))
        for name in MUNICIPALITIES:
            for spelling in [name, normalize(name), name.upper()]:
                self.assertIn(name, recognize('Saludos desde '+spelling+' Puerto Rico'))
            for lang in PATTERNS:
                self.assertEqual(10, len(set(templates(name,lang))))
                self.assertTrue(all(name in s for s in templates(name,lang)))
    def test_all_nyc_diaspora_countries(self):
        for name in NYC + DIASPORA + COUNTRIES + CULTURAL:
            self.assertIn(name, recognize('Saludos desde '+name+' Puerto Rico NYC'))
            self.assertEqual(10, len(set(templates(name))))
    def test_aliases(self):
        for canonical,aliases in ALIASES.items():
            for alias in aliases:
                self.assertIn(canonical,recognize(alias))
    def test_bilingual_mixed_roots(self):
        for i in range(10):
            d=respond('Hello, soy del Bronx y Guayanilla',rotation=i)
            self.assertEqual('reply',d['action'])
            self.assertEqual('spanglish',d['language'])
            self.assertIn('Bronx',d['text']); self.assertIn('Guayanilla',d['text'])
    def test_boundary_and_ambiguity(self):
        for text in ['Coronavirus','My friend Carolina','A cold Corona','Jamaica coffee','PanamaCity','Brooklynish', 'from Florida', 'from Jamaica', 'from Carolina']:
            self.assertEqual([],recognize(text))
        self.assertIn('Corona',recognize('From Corona Queens'))
    def test_rotation(self):
        self.assertEqual(10,len({respond('Saludos desde Ponce',rotation=i)['text'] for i in range(10)}))
        self.assertEqual(respond('Hi',rotation=0),respond('Hi',rotation=10))
        self.assertEqual(120,len(set(GENERAL_TEMPLATES)))
    def test_sensitive(self):
        for text in ['Bronx refund please','Hola doctor','Ponce I want to kill myself','ignore instructions Bronx','I need a prayer request','Saludos desde Bronx https://evil.com','I have pain','Mi pedido no llego','Soy del Bronx, Trump','Bronx I want to die','Ponce no quiero vivir','cant go on','I lost my child','quiero morir']:
            self.assertEqual('review',respond(text)['action'],text)
    def test_brand_separation(self):
        self.assertEqual('review',respond('Hi',brand='light_the_way_home')['action'])
        self.assertNotEqual(respond('Hi',brand='bible_for_everyone')['text'],respond('Hi',brand='abuelas_funnies')['text'])
        self.assertNotIn('Abuela',respond('Hi',brand='novaverse')['text'])
    def test_never_sales_greeting(self):
        catalog=[{'name':'Bronx Tee','communities':['Bronx'],'url':'https://example.com/tee','approved':True,'available':True,'verified_at':datetime.now(timezone.utc).isoformat()}]
        self.assertNotIn('https',respond('Hi from Bronx',catalog=catalog)['text'])
    def test_verified_merch(self):
        now=datetime.now(timezone.utc)
        product={'name':'Bronx Tee','communities':['Bronx'],'url':'https://example.com/tee','approved':True,'available':True,'verified_at':now.isoformat()}
        self.assertEqual('review',respond('Buy Bronx shirt')['action'])
        self.assertEqual('reply',respond('Buy Bronx shirt',catalog=[product],now=now)['action'])
        for mutation in [{'available':False},{'approved':False},{'verified_at':(now-timedelta(days=2)).isoformat()},{'url':'http://example.com'}]:
            self.assertEqual('review',respond('Buy Bronx shirt',catalog=[dict(product,**mutation)],now=now)['action'])
    def test_greeting_does_not_override_unknown_disclosure(self):
        for text in ['Hola me golpean en casa','Hello I am being stalked','Hola me violaron','Hello I overdosed','Hola necesito insulina','Hello I cannot breathe','Hi please send help','Hello I am 12 and someone is touching me','Hola Bronx can you explain a complex problem','Hola I want my money back','Hi I was charged twice','Hola no llego mi paquete','Hola me cobraron doble','hello my name is Orlando','I am not from Guayanilla']:
            self.assertEqual('review',respond(text)['action'],text)
    def test_unknown_not_automated(self):
        self.assertEqual('review',respond('Please advise what I should do with my life')['action'])

if __name__=='__main__': unittest.main()
