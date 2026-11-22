# unbranded rehearsal lab (MiroFish fork)

Fork of MiroFish (github.com/666ghj/MiroFish, Shanda-incubated, engine: CAMEL-AI OASIS).
What this fork changes:

1. **English everywhere.** The upstream UI already shipped a full English locale;
   this fork also translates the engine's brain: every LLM prompt (ontology design,
   persona generation, simulation config, report agent, interviews) and every memory
   episode written to Zep is now English. Backend and frontend default to English.
2. **Parsing made bilingual** where the engine inspects agent answers
   (question-number stripping, quote extraction) so English output is handled natively.
3. **.env.example** points at OpenAI-format endpoints: a mini-class model for the
   crowd, an optional boost model for the report agent.

## House rules (unbranded)
- Outputs are HYPOTHESES by definition. Nothing from this lab enters The Underwrite's
  record, a memo, or a client document. The bridge to evidence is a named real-world test.
- Seed material is public-tier only (public captures, published material, brand
  one-pagers). Client conversations stay out until contract cover says otherwise,
  because seeds travel to the LLM provider and Zep Cloud.
- Keep runs small: ~200 agents, <= 40 rounds. The cost lever is the model choice.

## Running it
Prereqs: Node 18+, Python 3.11-3.12, uv.
```
cp .env.example .env   # fill LLM_API_KEY + ZEP_API_KEY
npm run setup:all
npm run dev            # frontend :3000, backend :5001
```
Docker: `docker compose up -d` (same .env).
