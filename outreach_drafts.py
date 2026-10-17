"""Industry-specific outreach DRAFT generator. Never sends. Output is for Founder review.
Uses only verified fields from a lead row (name, category, city); makes no claims about the company's work
beyond its Google category. Same engine for every niche; copy lives in PROFILES (configuration)."""
import csv, sys

SENDER = "Ingrid, Lyra Sha AI | ingrid@lyrashaai.com"
FOOTER = ("\n--\n{sender}\n{address}\nIf you'd rather not hear from me, reply STOP and I won't contact you again.")

PROFILES = {
  "plumber": dict(label="plumbing", inquiry="a burst pipe, a backed-up drain or a water heater that quit",
                  pain="Callers with an urgent plumbing problem usually phone the next company when nobody answers.",
                  offer="Text-back and follow-up for missed calls and web inquiries, so urgent jobs are not lost while your crew is under a sink."),
  "landscaper": dict(label="landscaping", inquiry="a spring cleanup, sprinkler repair or a new yard project",
                  pain="Landscaping inquiries come in bursts, often while crews are out on jobs.",
                  offer="Quick replies and follow-ups on quote requests, so estimate requests turn into scheduled visits."),
  "window installer": dict(label="window installation", inquiry="a replacement quote for a few windows or a whole house",
                  pain="Window buyers usually collect several quotes and tend to go with whoever answers first.",
                  offer="Fast replies and follow-up on quote requests, with a simple way to book the in-home measure."),
  "insulation contractor": dict(label="insulation", inquiry="an attic or crawlspace insulation estimate",
                  pain="Insulation inquiries are often seasonal and homeowners compare a few estimates.",
                  offer="Prompt replies and follow-ups on estimate requests, so seasonal spikes are not missed."),
  "roofer": dict(label="roofing", inquiry="storm damage, a leak or a replacement estimate",
                  pain="After a storm, roof inquiries arrive all at once and the first company to respond usually wins the inspection.",
                  offer="Immediate replies and follow-up on inspection requests, including after-hours."),
  "hvac": dict(label="heating and cooling", inquiry="a furnace that stopped or an AC tune-up",
                  pain="No-heat and no-cool calls are urgent and often come after hours.",
                  offer="Text-back for missed calls and after-hours inquiries, with follow-up until the service visit is booked."),
  "well driller": dict(label="well drilling and pump service", inquiry="a well pump problem or a new well estimate",
                  pain="Rural customers with no water call until someone picks up.",
                  offer="Missed-call text-back and follow-up on estimate requests."),
}
GENERIC = dict(label="local service", inquiry="a service request", pain="Inquiries that go unanswered tend to go to the next company.",
               offer="Missed-call text-back and follow-up on inquiries.")

def draft(lead, niche_key, city, address="[POSTAL ADDRESS REQUIRED BEFORE SENDING]"):
    p = PROFILES.get(niche_key, GENERIC)
    subj = f"Quick question about {p['label']} inquiries in {city}"
    body = (f"Hello {lead['name']} team,\n\n"
            f"I'm reaching out to {p['label']} companies in {city}. {p['pain']}\n\n"
            f"We have a system designed to help local {p['label']} businesses respond to new inquiries faster, "
            f"recover missed opportunities, and turn more customer inquiries into booked jobs. {p['offer']}\n\n"
            f"I can't promise a specific number of leads or jobs. If it's useful, I can run a 7-day pilot and share what it recovers, "
            f"so you can judge by your own numbers.\n\nWould you be open to a short call this week?")
    return subj, body + FOOTER.format(sender=SENDER, address=address)

if __name__ == "__main__":
    path, niche, city = sys.argv[1:4]
    for r in csv.DictReader(open(path)):
        s, b = draft(r, niche, city)
        print("TO (verify before use):", r.get("website") or r.get("phone"), "\nSUBJECT:", s, "\n", b, "\n" + "=" * 60)
