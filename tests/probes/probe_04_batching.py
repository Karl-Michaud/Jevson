"""Claim (DESIGN §2.1, R13; PLAN Phase 0b probe 5): indexed references `items[i]` in batched
questions cause large error rates (27% at 150/request, 9% at 25/request) while keyed `items.k137`
(320/request) and one-item-per-question give 0/320.
Method: 320 words with controlled ground truth (100 unambiguous fruits, 220 non-fruits: animals,
tools, instruments, furniture, countries), shuffled with a fixed seed. Question: "Is `<ref>` the name
of a fruit?" Conditions:
  IDX-all-150 / IDX-all-25 : state {"items": [320 list]}, 150 or 25 questions per request
  IDX-chunk-150 / -25      : state {"items": [chunk]} re-indexed from 0 per request
  IDX-320                  : state list, all 320 questions in one request
  KEY-320                  : state {"items": {"k0":..}}, `items.k137`, one request
  KEY-150                  : keyed, 150 per request
  INLINE-320               : word inlined into the instruction, one request (state = short note)
  PER-REQ                  : one request per item, state = {"item": word} (320 requests)
Decision = noul > 0.5. Also diagnoses whether errors match a neighbour's truth (off-by-k)."""
import asyncio, json, random
from jevclient import Jev, save, fmt_rate
FRUITS = """apple banana cherry grape lemon lime mango orange peach pear pineapple plum strawberry
raspberry blueberry blackberry watermelon cantaloupe honeydew kiwi papaya apricot nectarine tangerine
clementine grapefruit pomegranate fig date guava lychee passionfruit persimmon quince gooseberry
cranberry currant elderberry mulberry boysenberry dragonfruit durian jackfruit rambutan longan
mangosteen starfruit kumquat loquat tamarillo feijoa soursop cherimoya sapodilla salak plantain
pomelo yuzu bilberry cloudberry lingonberry huckleberry jujube medlar ackee breadfruit mandarin
satsuma blood-orange damson greengage sloe physalis pitaya mamey lucuma marula miracle-fruit
jabuticaba santol langsat pulasan bael carambola cupuacu acerola pawpaw serviceberry salmonberry
marionberry loganberry tayberry calamansi bergamot citron ugli-fruit honeyberry muscadine olallieberry wineberry""".split()
NON = """dog cat horse cow sheep goat lion tiger bear wolf fox rabbit mouse eagle sparrow owl whale
dolphin shark salmon trout frog snake lizard turtle crocodile giraffe zebra elephant camel donkey
hammer screwdriver wrench pliers saw drill chisel ladder shovel rake axe crowbar mallet trowel
scissors stapler tape-measure level sander clamp violin cello piano guitar trumpet flute clarinet
oboe bassoon trombone tuba harp drum xylophone banjo ukulele accordion harmonica saxophone mandolin
chair table sofa bed desk wardrobe bookshelf stool bench cabinet dresser armchair ottoman nightstand
futon hammock couch recliner cupboard sideboard France Germany Spain Italy Portugal Norway Sweden
Finland Poland Austria Greece Turkey Egypt Kenya Nigeria Brazil Argentina Chile Peru Mexico Canada
Japan China India Vietnam Thailand Australia Iceland Ireland Belgium bicycle car truck bus train
airplane boat scooter tractor submarine helicopter canoe kayak skateboard motorcycle tram ferry
yacht glider rocket pencil pen eraser notebook ruler envelope stamp calculator lamp clock mirror
pillow blanket towel curtain carpet vase kettle toaster blender spoon fork knife plate bowl cup
mug teapot jar bottle basket bucket brick concrete granite marble copper iron silver gold steel
glass plastic rubber leather wool cotton silk nylon paper cardboard volcano glacier canyon desert
river lake ocean island mountain valley swamp forest meadow cliff beach cave reef marsh tundra prairie hill plateau fjord lagoon delta dune geyser crater""".split()
assert len(FRUITS) == 100, len(FRUITS)
NON = NON[:220]; assert len(NON) == 220, len(NON)
rng = random.Random(42)
ITEMS = [(w, True) for w in FRUITS] + [(w, False) for w in NON]
rng.shuffle(ITEMS)
WORDS = [w for w, _ in ITEMS]; TRUTH = [t for _, t in ITEMS]
Q = "Is {} the name of a fruit?"
def nq(ref): return {"type": "noul", "instructions": Q.format(ref)}

async def run_cond(j, name, reqs):
    """reqs: list of (state, {qkey: (global_idx, question)})"""
    pred = {}
    res = await asyncio.gather(*[j.ask(s, {k: q for k, (_, q) in m.items()}) for s, m in reqs])
    lat = []
    for (s, m), r in zip(reqs, res):
        lat.append(r["latency_s"])
        assert r["status"] == 200, r
        for k, (gi, _) in m.items():
            pred[gi] = r["body"]["answers"][k]["noul"]
    wrong = [i for i in range(320) if (pred[i] > 0.5) != TRUTH[i]]
    near = sum(1 for i in wrong if any(0 <= i + d < 320 and TRUTH[i + d] == (pred[i] > 0.5) for d in (-2, -1, 1, 2)))
    unsure = sum(1 for i in range(320) if 0.2 < pred[i] < 0.8)
    return {"cond": name, "requests": len(reqs), "wrong": len(wrong), "rate": fmt_rate(len(wrong), 320),
            "wrong_items": [(i, WORDS[i], pred[i]) for i in wrong], "unsure_0.2-0.8": unsure,
            "wrong_consistent_with_neighbor": near, "latency_s": lat, "pred": pred}

def chunks(n): return [list(range(a, min(a + n, 320))) for a in range(0, 320, n)]

async def main(per_req=True):
    j = Jev(concurrency=8); out = {"words": WORDS, "truth": TRUTH}
    L = {"items": WORDS}
    conds = {}
    for n in (150, 25):
        conds[f"IDX-all-{n}"] = [(L, {f"q{i}": (i, nq(f"`items[{i}]`")) for i in c}) for c in chunks(n)]
        conds[f"IDX-chunk-{n}"] = [({"items": [WORDS[i] for i in c]}, {f"q{i}": (i, nq(f"`items[{p}]`")) for p, i in enumerate(c)}) for c in chunks(n)]
    conds["IDX-320"] = [(L, {f"q{i}": (i, nq(f"`items[{i}]`")) for i in range(320)})]
    K = {"items": {f"k{i}": w for i, w in enumerate(WORDS)}}
    conds["KEY-320"] = [(K, {f"q{i}": (i, nq(f"`items.k{i}`")) for i in range(320)})]
    conds["KEY-150"] = [(K, {f"q{i}": (i, nq(f"`items.k{i}`")) for i in c}) for c in chunks(150)]
    conds["INLINE-320"] = [("Classify each word.", {f"q{i}": (i, nq(f"the word '{WORDS[i]}'")) for i in range(320)})]
    if per_req:
        conds["PER-REQ"] = [({"item": WORDS[i]}, {"q": (i, nq("`item`"))}) for i in range(320)]
    for name, reqs in conds.items():
        r = await run_cond(j, name, reqs); out[name] = r
        print(f"{name:14s} req={r['requests']:3d} wrong={r['rate']} unsure={r['unsure_0.2-0.8']} nbr={r['wrong_consistent_with_neighbor']} ex={r['wrong_items'][:6]}")
    await j.aclose(); save("p04_batching", out); print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
