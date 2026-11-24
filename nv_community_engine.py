"""Zero-token community reply policy. Transport, durable state and account identity belong to caller.
Sources (names only, no inferred cultural facts):
https://www.pr.gov/gobierno-2/directorio-municipios
https://www.nyc.gov/assets/planning/download/pdf/data-maps/city-neighborhoods/dcp-city-of-neighborhoods-2022.pdf
Street aliases additionally verified: Grand Concourse (Bronx), NYC LPC report
https://s-media.nyc.gov/agencies/lpc/lp/2403.pdf
Avenue C / Loisaida Avenue, Loisaida Inc.
https://loisaida.org/venue/avenue-c-loisaida-ave-2/
Landmarks: https://nycgovparks.org/parks/pelhambaypark/facilities/beaches
https://nycgovparks.org/parks/pelhambaypark
https://www.mlb.com/yankees/ballpark/information/directions-parking
Fordham Road: https://www.nyc.gov/site/bronxcb5/about/our-neighborhoods.page
Aliases explicitly commissioned in the Founder addendum are accepted as self-identification.
"""
import re
import unicodedata
from datetime import datetime, timezone

def normalize(text):
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))).strip()

def contains(text, phrase):
    return (' ' + normalize(phrase) + ' ') in (' ' + text + ' ')

MUNICIPALITIES = ('Adjuntas|Aguada|Aguadilla|Aguas Buenas|Aibonito|Añasco|Arecibo|Arroyo|Barceloneta|Barranquitas|Bayamón|Cabo Rojo|Caguas|Camuy|Canóvanas|Carolina|Cataño|Cayey|Ceiba|Ciales|Cidra|Coamo|Comerío|Corozal|Culebra|Dorado|Fajardo|Florida|Guánica|Guayama|Guayanilla|Guaynabo|Gurabo|Hatillo|Hormigueros|Humacao|Isabela|Jayuya|Juana Díaz|Juncos|Lajas|Lares|Las Marías|Las Piedras|Loíza|Luquillo|Manatí|Maricao|Maunabo|Mayagüez|Moca|Morovis|Naguabo|Naranjito|Orocovis|Patillas|Peñuelas|Ponce|Quebradillas|Rincón|Río Grande|Sabana Grande|Salinas|San Germán|San Juan|San Lorenzo|San Sebastián|Santa Isabel|Toa Alta|Toa Baja|Trujillo Alto|Utuado|Vega Alta|Vega Baja|Vieques|Villalba|Yabucoa|Yauco').split('|')
NYC = ('Bronx|Brooklyn|Manhattan|Queens|Staten Island|South Bronx|Mott Haven|Hunts Point|Morrisania|Soundview|Castle Hill|Parkchester|Fordham|Tremont|Kingsbridge|Pelham Parkway|Highbridge|Melrose|East Harlem|Lower East Side|Washington Heights|Inwood|Bushwick|Williamsburg|Sunset Park|East New York|Brownsville|Jackson Heights|Corona|Elmhurst|Jamaica|Astoria').split('|')
DIASPORA = ('Orlando|Kissimmee|Tampa|Philadelphia|Newark|Hartford|Bridgeport|Chicago|Boston|Perth Amboy').split('|')
COUNTRIES = ('Puerto Rico|Dominican Republic|Cuba|Mexico|Colombia|Venezuela|Panama|Ecuador|Peru|Honduras|Guatemala|El Salvador|Nicaragua|Costa Rica|Argentina|Chile|Bolivia|Paraguay|Uruguay').split('|')
CULTURAL = ['Nuyorican', 'Boricua', 'New York roots', 'Barrio roots', 'Puerto Rican roots', 'Dominican roots']
ALIASES = {
 'Bronx': ['BX', 'Boogie Down Bronx', 'Boogie Down', 'Bronx born and raised', 'the Bronx', 'Grand Concourse', 'Orchard Beach', 'Pelham Bay Park', 'Yankee Stadium'],
 'Fordham': ['Fordham Road', 'Fordham Rd'],
 'East Harlem': ['Spanish Harlem', 'El Barrio'], 'Lower East Side': ['Loisaida', 'Loisaida Avenue', 'Loisaida Ave', 'Avenue C'],
 'Ponce': ['La Perla del Sur', 'Ciudad Señorial'], 'Guayanilla': ['Tierra de Agüeybaná'],
 'Mayagüez': ['La Sultana del Oeste'], 'Vieques': ['Isla Nena'], 'Caguas': ['La Ciudad Criolla'],
 'Bayamón': ['El Pueblo del Chicharrón'], 'Orocovis': ['Corazón de Puerto Rico'],
 'Yauco': ['El Pueblo del Café'], 'Rincón': ['El Pueblo de los Bellos Atardeceres'],
 'Nuyorican': ['Newyorican', 'Nuyoricans', 'Newyoricans'], 'Boricua': ['Boricuas'],
 'New York roots': ['NYC raised', 'New York born and raised', 'NYC born and raised'],
 'Barrio roots': ['from the barrio'], 'Puerto Rican roots': ['Puerto Rican', 'puertorriqueño', 'puertorriqueña'],
 'Dominican roots': ['Dominican from', 'Dominicana de', 'Dominicano de'],
 'Dominican Republic': ['República Dominicana'], 'Mexico': ['México'], 'Panama': ['Panamá'], 'Peru': ['Perú'],
 'Philadelphia': ['Philly'],
}
# Do not infer a municipality from an ordinary word/person name or a state/country collision.
AMBIGUOUS = {'Arroyo','Carolina','Ceiba','Cidra','Culebra','Dorado','Florida','Isabela','Lajas','Lares','Las Piedras','Manatí','Moca','Naranjito','Patillas','Rincón','Río Grande','Salinas','San Juan','San Lorenzo','San Sebastián','Santa Isabel','Villalba','Corona','Jamaica','Inwood','Melrose','Williamsburg','Brownsville','Newark','Chile'}
PLACE_CUES = ['from', 'de', 'desde', 'born', 'raised', 'vivo en', 'live in', 'living in', 'saludos', 'presente', 'nyc', 'queens', 'bronx', 'puerto rico', 'pr', 'barrio', 'municipio', 'roots', 'raices']
BRANDS = {'trending_edit', 'de_mi_pueblo', 'abuelas_funnies', 'geriatric_teen_mom', 'bible_for_everyone', 'lyra_sha_ai', 'novaverse'}

PATTERNS = {
 'es': [
  '¡{community} presente! Qué alegría tenerte por aquí.', 'Un abrazo enorme, {community}.',
  '¡Saludos, {community}! Gracias por pasar a compartir.', '¡Qué lindo ver a {community} por aquí!',
  '{community}, aquí hay espacio para tus historias. ¿Qué recuerdo te hizo sonreír hoy?',
  'Cariño para {community}. Gracias por dejarnos tu saludo.', '¡{community}, te leemos con mucho cariño!',
  'Un saludo lleno de cariño para {community}. ¿Qué te gusta compartir de tus raíces?',
  '¡{community}, qué alegría encontrarnos por aquí!', '¡{community}! Un abrazo de esos que se sienten cerquita.'
 ],
 'en': [
  '{community} is here! So glad you stopped by.', 'Sending a big hug, {community}.',
  'Hello, {community}! Thanks for sharing a little of home with us.', 'Love seeing {community} here!',
  '{community}, there’s room for your stories here. What memory made you smile today?',
  'A little love for {community}. Thanks for saying hello.', '{community}, we’re happy you’re here!',
  'A warm hello to {community}. What do you love sharing about your roots?',
  '{community}, so good to connect with you!', '{community}! Sending one of those hugs that feels like home.'
 ],
 'spanglish': [
  '¡{community} presente! So happy you’re here.', 'Sending un abrazo grande to {community}.',
  '¡Saludos, {community}! Thanks for stopping by.', '{community} in the house. ¡Qué alegría!',
  '{community}, tell us a little memory. Te leemos con cariño.', 'A little love for {community}. ¡Gracias por tu saludo!',
  '¡{community}! You brought a little home with you.', 'Hello, {community}. ¡Un abrazo para nuestra gente!',
  'So good to see {community} here. ¿Qué recuerdo te hizo sonreír hoy?', '¡{community}! Sending cariño right back.'
 ]
}

def templates(community, language='es'):
    return [s.format(community=community) for s in PATTERNS[language]]

# 120 independently worded general replies, divided by language and intent.
GENERAL = {
 'hello': {
 'es': ['¡Hola! Qué alegría leerte.', '¡Saludos! Pasa, aquí hay cariño.', '¡Hola! Gracias por ese saludito.', '¡Qué bueno tenerte por aquí!', '¡Un abrazo! ¿Cómo va tu día?', '¡Hola, nuestra gente! Te leemos.', '¡Saludos con mucho cariño!', '¡Hola! Aquí estamos, cafecito en mano.', '¡Qué lindo encontrarnos por aquí!', '¡Hola! Que tengas un día bonito.'],
 'en': ['Hello! So happy to hear from you.', 'Hi there! Sending a little love your way.', 'Hey! Thanks for stopping by.', 'So glad you’re here!', 'Hello! How’s your day going?', 'Hi! There’s always room for a kind hello.', 'Sending a warm hello right back!', 'Hey there! Coffee in hand over here.', 'Good to see you here!', 'Hello! Hope your day has something sweet in it.'],
 'spanglish': ['¡Hola! So glad you’re here.', 'Hey! Un abrazo para ti.', '¡Saludos! How’s your day going?', 'Hello, nuestra gente!', '¡Qué alegría! Thanks for stopping by.', 'Hi! Aquí hay cariño.', '¡Hola! Sending love right back.', 'Hey there! Cafecito listo.', '¡Saludos! Good to see you.', 'Hello! Que tengas un día bonito.']},
 'thanks': {
 'es': ['¡Gracias a ti por estar aquí!', '¡De corazón, gracias!', 'Ese cariño se siente. ¡Gracias!', '¡Gracias por acompañarnos!', 'Un abrazo y gracias por tu mensaje.', '¡Gracias por compartir con nosotros!', 'Qué lindo gesto. ¡Gracias!', '¡Se agradece mucho tu cariño!', 'Gracias por regalarnos un ratito de tu día.', '¡Gracias! Aquí te leemos con cariño.'],
 'en': ['Thank you for being here!', 'Thanks from the heart!', 'That kindness means a lot. Thank you!', 'Thanks for keeping us company!', 'A hug and a thank you for your message.', 'Thanks for sharing with us!', 'That’s so kind. Thank you!', 'We appreciate your warmth!', 'Thanks for giving us a moment of your day.', 'Thank you! Sending that love right back.'],
 'spanglish': ['¡Gracias! Happy you’re here.', 'Thank you, de corazón.', '¡Qué cariño! Thank you.', 'Thanks for being aquí con nosotros.', 'Un abrazo, and thank you.', '¡Gracias por compartir! Means a lot.', 'So kind of you. ¡Gracias!', 'We feel that cariño. Thank you!', 'Thanks for a little of your día.', '¡Gracias! Sending cariño right back.']},
 'reaction': {
 'es': ['¡Ese cariño llegó!', '¡Un corazón de vuelta para ti!', '¡Qué lindo mensaje!', '¡Esa risa se pega!', '¡Gracias por esa alegría!', '¡Un abrazo enorme!', '¡Qué bonito compartir este ratito!', '¡Aquí sonriendo contigo!', '¡Cariño del bueno para ti!', '¡Qué alegría nos dejaste!'],
 'en': ['That love reached us!', 'A heart right back to you!', 'What a sweet message!', 'That laugh is catching!', 'Thanks for that little bit of joy!', 'Sending a big hug!', 'So nice to share this moment!', 'Smiling with you over here!', 'Sending you a little extra love!', 'You left us with a smile!'],
 'spanglish': ['That cariño reached us!', 'Un corazón right back!', '¡Qué lindo! Thanks for that.', 'That laugh, ¡se pega!', '¡Gracias! You brought joy.', 'Sending un abrazo enorme!', 'This little ratito means a lot.', 'Smiling contigo!', 'Cariño del bueno, coming your way!', 'You left us smiling. ¡Qué alegría!']},
 'roots': {
 'es': ['Las raíces se llevan en el corazón.', 'Hay recuerdos que llegan con un abrazo.', '¡Qué bonito compartir de dónde venimos!', 'La distancia no borra el cariño.', 'Esos recuerdos de casa se sienten cerquita.', '¡Gracias por compartir tus raíces!', 'Qué lindo guardar esos recuerdos.', 'Hay un pedacito de casa en esas palabras.', '¡Un abrazo para esa nostalgia!', 'Qué bonito encontrarnos a través de nuestras historias.'],
 'en': ['We carry our roots in our hearts.', 'Some memories arrive with a hug.', 'It’s beautiful to share where we come from.', 'Distance doesn’t erase that love.', 'Those memories of home feel close.', 'Thanks for sharing your roots!', 'Those memories are worth holding close.', 'There’s a little piece of home in those words.', 'Sending a hug for that homesick feeling.', 'So good to connect through our stories.'],
 'spanglish': ['Our raíces stay in the heart.', 'Some recuerdos feel like un abrazo.', 'So beautiful to share de dónde venimos.', 'La distancia can’t erase that cariño.', 'Those memories de casa feel close.', 'Thanks for sharing tus raíces!', 'Hold those recuerdos cerquita.', 'A little piece de casa in those words.', 'Sending un abrazo for that nostalgia.', 'Our historias brought us together.']}}
GENERAL_TEMPLATES = [v for category in GENERAL.values() for language in category.values() for v in language]

SAFETY = re.compile(r'\b(fuck\w*|bitch\w*|cabron\w*|pendej\w*|mierda|shoot\w*|dispar\w*|idiot|stupid|hate|odio|racis\w*|suicid\w*|kill\w*|murder\w*|matar\w*|amenaz\w*|hurt|threat\w*|harass\w*|abuse\w*|assault\w*|rape\w*|cancer|medical|medicin\w*|doctor|diagnos\w*|pain|pregnan\w*|embaraz\w*|dolor|enferm\w*|medic\w*|refund\w*|reembolso\w*|chargeback|payment|complaint\w*|scam\w*|estafa\w*|order|pedido|cobro\w*|disput\w*|politic\w*|election|trump|biden|democrat\w*|republican\w*|prayer request|pray for|oren por|oracion|missing|desaparecid\w*|died|dead|murio|falleci\w*|depress\w*|ansiedad|anxiety|ignore|instructions|system prompt|api key|access token|password|contrasena|secret|secreto|http|https|address|direccion|phone|telefono)\b')
PRODUCT = re.compile(r'\b(buy|purchase|shop|price|pricing|cost|sizing|size|available|availability|shipping|merch|shirt|hoodie|design|compr\w*|precio\w*|cuanto|talla\w*|disponib\w*|envio|camisa\w*|diseno\w*)\b')

def language_of(text):
    n = normalize(text)
    es = any(contains(n, p) for p in ['hola','saludos','desde','soy','gracias','buenos dias','buenas tardes','buenas noches','bendiciones','hermoso','hermosa','mi pueblo','de','presente','que','vivo','raices','naci','me encanta'])
    en = any(contains(n, p) for p in ['hello','hi','hey','from','born','raised','thanks','thank you','beautiful','love','live','roots','my','in the','and'])
    return 'spanglish' if es and en else 'es' if es else 'en'

def recognize(text):
    n = normalize(text)
    result = []
    cue = any(contains(n, c) for c in PLACE_CUES)
    pr_context = any(contains(n,c) for c in ['puerto rico','pr','municipio'])
    ny_context = any(contains(n,c) for c in ['nyc','new york','queens','bronx','brooklyn','neighborhood','barrio'])
    for c in MUNICIPALITIES + NYC + DIASPORA + COUNTRIES + CULTURAL:
        disambiguated = (pr_context if c in {'Florida','Carolina','San Juan','San Lorenzo','San Sebastián','Santa Isabel','Villalba','Isabela','Moca','Salinas','Río Grande'} else ny_context if c in {'Jamaica','Corona','Inwood','Melrose','Williamsburg','Brownsville'} else cue)
        if contains(n, c) and (c not in AMBIGUOUS or disambiguated):
            result.append(c)
        elif any(contains(n, a) for a in ALIASES.get(c, [])):
            result.append(c)
    # A specific neighborhood is more useful than its encompassing borough, but retain distinct mentions.
    return list(dict.fromkeys(result))

# A matching greeting/place never licenses a reply to arbitrary extra prose.
# Strip known identity/location phrases, then accept only low-risk social language.
LOW_RISK_WORDS = set("hola hello hi hey saludos saludo saludar desde soy somos de del la el los las un una para por y o en con mi mis tu tus su sus nuestra nuestro nuestros nuestras gente familia pueblo barrio municipio comunidad raices roots pride proud orgullo orgullosa orgulloso boricua nuyorican puertorriqueno puertorriquena dominicano dominicana born raised from live living in i im m am was the a an and my our your here there present presente today hoy siempre siempre gracias thank thanks you te ti todos todas mucho mucha mucho muchos muchas tanto tan lindo linda lindos lindas hermoso hermosa beautiful amazing nice cute love loving loved me encanta amo extrano extrana miss missing nostalgia nostalgic recuerdo recuerdos recordar memories memory home casa island isla viva que alegria feliz felicidades good morning afternoon evening night buenos buenas dias tardes noches dia bendiciones bendicion bless blessed blessings god dios jesus amen corazon corazones heart hearts abrazo abrazos hug hugs jajaja jajajaja haha hahaha lol funny sonrisa sonrisas risas risa laugh laughing smile smiles happy great wonderful awesome yes si claro eso asi tambien too bien bueno buena aqui alla alla alla all so very really just only always still back us nos al hasta es son ser estar estoy estamos nacido nacida naci grew up raised origin originally now actualmente right shout out checking sending send big warm little heartwarming buy purchase shop price pricing cost sizing size sizes available availability shipping merch shirt shirts hoodie hoodies design designs comprar compra compras precio precios cuanto talla tallas disponible disponibles envio camisa camisas diseno disenos can could where how much do does have has this that it want would like please friend friends amigos amigas mama papa abuela abuelo abuelos padres mother father parents grandmother grandfather family hometown ny new york newyork puerto rico pr nyc bx 100".split())

def low_risk_social(text):
    residue = normalize(text)
    phrases = MUNICIPALITIES + NYC + DIASPORA + COUNTRIES + CULTURAL
    phrases += [a for aliases in ALIASES.values() for a in aliases]
    # Longest first prevents partial removal from leaving an unknown fragment.
    for phrase in sorted(phrases, key=lambda p: len(normalize(p)), reverse=True):
        residue = re.sub(r'(?<![a-z0-9])' + re.escape(normalize(phrase)) + r'(?![a-z0-9])', ' ', residue)
    return set(residue.split()).issubset(LOW_RISK_WORDS)

def respond(text, brand='trending_edit', rotation=0, catalog=None, now=None):
    """Return a decision only. Never dispatch, log raw comments or alter state.

    catalog entries require name, communities, url, available=True, verified_at,
    approved=True. Verification expires after 24 hours. No price/stock claims generated.
    """
    if not isinstance(text, str) or not text.strip():
        return {'action':'ignore', 'reason':'empty', 'text':'', 'communities':[], 'language':'en'}
    brand = {'gtm':'geriatric_teen_mom', 'bible':'bible_for_everyone'}.get(brand,brand)
    n = normalize(text)
    lang = language_of(text)
    communities = recognize(text)
    base = {'text':'', 'communities':communities, 'language':lang}
    if brand not in BRANDS:
        return dict(base, action='review', reason='brand_not_authorized')
    if len(text) > 1000 or SAFETY.search(n) or any(contains(n,p) for p in ['want to die','cant go on','can t go on','give up','quiero morir','no quiero vivir','me quiero matar','lost my child','lost my baby','perdi a mi hijo','perdi a mi hija','perdi mi bebe','mi esposo me pega','mi esposa me pega','me voy a quitar la vida','sexually assaulted']) or re.search(r'\d{3}[- .]?\d{3}[- .]?\d{4}',text):
        return dict(base, action='review', reason='sensitive_or_untrusted')
    if not low_risk_social(text):
        return dict(base, action='review', reason='substantive_unrecognized_content')
    if PRODUCT.search(n):
        valid = []
        current = now or datetime.now(timezone.utc)
        for p in catalog or []:
            try:
                verified = datetime.fromisoformat(p['verified_at'].replace('Z','+00:00'))
                age = (current - verified).total_seconds()
                if p.get('approved') is True and p.get('available') is True and 0 <= age <= 86400 and p['url'].startswith('https://') and set(p['communities']).intersection(communities):
                    valid.append(p)
            except (KeyError, TypeError, ValueError):
                continue
        if not valid:
            return dict(base, action='review', reason='product_requires_verified_catalog')
        p = valid[rotation % len(valid)]
        copy = {'en':f"You can take a look at {p['name']} here: {p['url']}", 'es':f"Puedes ver {p['name']} aquí: {p['url']}", 'spanglish':f"Take a look at {p['name']} aquí: {p['url']}"}[lang]
        return dict(base, action='reply', reason='verified_product_request', text=copy)
    if communities:
        # Mixed NY + PR is deliberately prioritized even if another country/city is also mentioned.
        ny = sorted([c for c in communities if c in NYC], key=len, reverse=True)
        pr = [c for c in communities if c in MUNICIPALITIES]
        chosen = list(dict.fromkeys(([ny[0], pr[0]] if ny and pr else communities[:2])))
        label = (' y ' if lang == 'es' else ' + ').join(chosen)
        copy = templates(label, lang)[rotation % 10]
    else:
        if any(contains(n, p) for p in ['gracias','thanks','thank you']): cat='thanks'
        elif any(contains(n, p) for p in ['nostalgia','extrano','miss','roots','raices','pride','orgullo']): cat='roots'
        elif any(contains(n, p) for p in ['hola','hello','hi','hey','buenos dias','buenas tardes','buenas noches','bendiciones']): cat='hello'
        elif any(contains(n, p) for p in ['beautiful','hermoso','hermosa','jajaja','haha','lol','lindo','love']) or any(c in text for c in ['❤','♥','🇵🇷','😂','😍']): cat='reaction'
        else: return dict(base, action='review', reason='unrecognized_intent')
        copy = GENERAL[cat][lang][rotation % 10]
    # Personalities stay account-scoped; heritage language is only used on commissioned cultural brands.
    if brand in {'lyra_sha_ai','novaverse'}:
        copy = {'en':'Thanks for connecting with us! Glad you’re here.', 'es':'¡Gracias por conectar con nosotros! Qué bueno tenerte aquí.', 'spanglish':'Thanks for connecting. ¡Qué bueno tenerte aquí!'}[lang]
    elif brand == 'bible_for_everyone':
        copy = {'en':'God bless you! So glad you’re here with us.', 'es':'¡Dios te bendiga! Qué alegría tenerte por aquí.', 'spanglish':'God bless you. ¡Qué alegría tenerte aquí!'}[lang]
    elif brand == 'abuelas_funnies':
        copy += {'en':' Abuela saved you a little spot here.', 'es':' Abuela te guardó un rinconcito aquí.', 'spanglish':' Abuela saved you un rinconcito.'}[lang]
    elif brand == 'geriatric_teen_mom':
        copy += {'en':' A little laugh together does us good.', 'es':' Una risita en compañía nos viene bien.', 'spanglish':' A little risita together nos viene bien.'}[lang]
    return dict(base, action='reply', reason='community' if communities else 'greeting', text=copy)
