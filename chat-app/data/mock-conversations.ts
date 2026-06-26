// Mock answers used by the scaffold. Wiring to retrieval + Anthropic happens in a
// follow-up; ADR-007 (quote-first) is the contract these answers honor for
// doctrinal Q&A; ADR-010 amends that contract for meta Q&A (plain prose).
//
// Quotes are taken verbatim from
// 01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature/en/text.md.

export type Lang = "en" | "mr";

export type Quote = {
  // The verbatim passage from the corpus.
  body: string;
  // Attribution that lives directly under the quote (no separate [#N] markers).
  workTitle: string;
  location: string;
  kind: "canonical" | "athvani" | "biography";
  author: string;
  // Optional short gloss in the user's language when the quote is in a
  // different language. Clearly a paraphrase, not the source.
  paraphrase?: string;
  // Server-filled: the work_id for the source work. Non-empty only for
  // canonical quotes that had a matching chunk. Used by QuoteBlock to render
  // a "Read in full" link to /read/{workId}. Empty string or absent for
  // athvani / biography / quotes without a chunk match.
  workId?: string;
  // Server-filled: 1-based page in the reading surface where the cited
  // passage appears. When present, the "Read in full" link opens the reader
  // directly at this page instead of page 1.
  readPage?: number;
};

// In Q&A mode each quote is paired with a short rationale explaining why
// this particular passage was surfaced (user feedback 2026-06-15: "after
// each citation, add a line about why that example was taken"). The
// rationale lives on QAAnswer (not on Quote itself) so Quote stays the
// generic passage record reusable across modes.
export type QACitation = {
  quote: Quote;
  whyChosen: string;
};

// Lightweight reference used by meta-mode Q&A: a work the answer drew on
// without quoting verbatim. Per ADR-010, meta answers cite works by title
// (and optional location/author) rather than blockquote.
export type Reference = {
  workTitle: string;
  location?: string;
  author?: string;
};

// QAAnswer carries both doctrinal and meta shapes (ADR-010). The UI
// branches on `citations.length`:
//   - citations.length > 0  -> doctrinal: framing + quote blocks + optional synthesis
//   - citations.length === 0 -> meta: framing as the answer paragraph + optional references
// `classification` is emitted by the LLM for audit; the UI does not switch on it.
export type QAAnswer = {
  kind: "qa";
  classification?: "doctrinal" | "meta";
  question: string;
  framing: string;
  // Optional paragraph array for longer meta answers (mirrors the
  // pydantic schema in tools/schemas.py). UI prefers this when present.
  framingParagraphs?: string[];
  citations: QACitation[];
  references?: Reference[];
  synthesis?: string;
};

// Pravachan revised 2026-06-14 per user feedback. Structure is now:
//   Your question (verbatim)  →  Thesis  →  Gurudev's words  →  Examples
// "Suggested sequence" was dropped — the devotee orders the material themselves.
// Each example carries a "why this example" rationale + a read-in-full link slug
// that opens Simple Reading mode at the source.
export type PravachanExample = {
  title: string;
  // Optional one-line gloss when the athvani is too long to quote in full.
  gloss?: string;
  // The verbatim athvani quote + attribution (rendered like Q&A blockquotes).
  quote: Quote;
  // Single sentence explaining how this example illustrates the thesis.
  whyThisExample: string;
  // The Simple Reading mode slug this opens to. UI renders [→ Read in full].
  readSlug?: string;
};

export type PravachanAnswer = {
  kind: "pravachan";
  // The user's question, restated verbatim at the top of the brief.
  question: string;
  // The framing thesis — 1–2 sentences in the assistant's voice. Optional
  // because not every Pravachan question warrants a thesis (e.g., "share
  // some athvanis on X" goes straight to the list). User feedback 2026-06-15:
  // structure should follow the question.
  thesis?: string;
  // ONE verbatim canonical passage that grounds the thesis. Same caveat —
  // optional when the question is athvani-collection style.
  gurudevsWords?: Quote;
  // 3–5 athvani examples.
  examples: PravachanExample[];
};

export type Conversation = {
  id: string;
  defaultMode: "qa" | "pravachan" | "reading";
  answer: QAAnswer | PravachanAnswer;
};

// ---------------------------------------------------------------------------
// 1. Q&A doctrinal — "What are Shri Gurudev's views on Bhakti?"
//    Two real PGHL quotes; brief synthesis at end per ADR-007.
//    Per-language variants so the chat surface is language-blind — it just
//    renders whatever the API returned.
// ---------------------------------------------------------------------------

const qaBhaktiEn: QAAnswer = {
  kind: "qa",
  classification: "doctrinal",
  question: "What are Shri Gurudev's views on Bhakti?",
  framing: "Here is what the literature says on this:",
  citations: [
    {
      quote: {
        body:
          "Mysticism denotes that attitude of mind which involves a direct, immediate, intuitive apprehension of God. It signifies the highest attitude of which man is capable, namely, a beatific contemplation of God, and its dissemination in the Society and the World. The surest criterion of mysticism is the reality of the experience as enjoyed by the mystic himself. It is known only to him and to his Maker. Before it there is no appeal; for it there is no criterion.",
        workTitle: "Pathway to God in Hindi Literature",
        location: "General Introduction",
        kind: "canonical",
        author: "Shri Gurudev",
      },
      whyChosen:
        "Gurudev's foundational definition of bhakti as the lived, intuitive apprehension of God — the frame within which every other passage on bhakti sits.",
    },
    {
      quote: {
        body:
          "Kabir surpasses other Hindi saints in his description of the spiritual Teacher with his moral, mystical and social qualities. He has laid great stress on the importance of the Name of God. He would require us to meditate in silence and not call upon God in a loud tone; he would also advise us to meditate internally and by the help of the breath, and one of the tests for the reality of our spiritual development would, according to him, be that the Name would reveal itself before our vision or audition.",
        workTitle: "Pathway to God in Hindi Literature",
        location: "General Introduction — Kabir summary",
        kind: "canonical",
        author: "Shri Gurudev",
      },
      whyChosen:
        "Gurudev's reading of Kabir grounds the definition in practice — Name, breath, the Teacher — showing how bhakti is actually lived day-to-day.",
    },
  ],
  synthesis:
    "Taken together, these passages frame bhakti as the lived intuitive apprehension of God, sustained by the Name and the inward guidance of the Teacher.",
};

const qaBhaktiMr: QAAnswer = {
  kind: "qa",
  classification: "doctrinal",
  question: "श्री गुरुदेव भक्तीविषयी काय सांगतात?",
  framing: "साहित्यात या विषयावर हे सांगितले आहे:",
  citations: [
    {
      // Verbatim quote body stays in its original language per ADR-007.
      quote: {
        body:
          "Mysticism denotes that attitude of mind which involves a direct, immediate, intuitive apprehension of God. It signifies the highest attitude of which man is capable, namely, a beatific contemplation of God, and its dissemination in the Society and the World. The surest criterion of mysticism is the reality of the experience as enjoyed by the mystic himself. It is known only to him and to his Maker. Before it there is no appeal; for it there is no criterion.",
        workTitle: "Pathway to God in Hindi Literature",
        location: "General Introduction",
        kind: "canonical",
        author: "Shri Gurudev",
      },
      whyChosen:
        "गुरुदेवांची भक्तीची मूलभूत व्याख्या — ईश्वराची प्रत्यक्ष, अंतर्ज्ञानात्मक अनुभूती. भक्तीवरील प्रत्येक पुढचा उतारा याच्या अनुषंगाने उभा आहे.",
    },
    {
      quote: {
        body:
          "Kabir surpasses other Hindi saints in his description of the spiritual Teacher with his moral, mystical and social qualities. He has laid great stress on the importance of the Name of God. He would require us to meditate in silence and not call upon God in a loud tone; he would also advise us to meditate internally and by the help of the breath, and one of the tests for the reality of our spiritual development would, according to him, be that the Name would reveal itself before our vision or audition.",
        workTitle: "Pathway to God in Hindi Literature",
        location: "General Introduction — Kabir summary",
        kind: "canonical",
        author: "Shri Gurudev",
      },
      whyChosen:
        "कबीराच्या वाचनातून गुरुदेव दाखवतात की भक्ती दैनंदिन व्यवहारात कशी उतरते — नाम, श्वास, सद्गुरू.",
    },
  ],
  synthesis:
    "एकत्रितपणे या उतार्‍यांतून भक्ती ही ईश्वराची जीवंत, अंतर्ज्ञानी अनुभूती असून, नामाद्वारे आणि सद्गुरूच्या अंतर्बाह्य मार्गदर्शनाद्वारे टिकवली जाते — असे या साहित्याचे प्रतिपादन.",
};

// ---------------------------------------------------------------------------
// 2. Q&A meta — "Who was Bhausaheb Maharaj?"
//    Per ADR-010: plain prose answer, optional references, no quote blocks.
//    Mock kept deliberately general — dates and specific lineage details are
//    intentionally hedged ("19th-century saint...") until the real backend
//    grounds these claims in the biographical chunks.
// ---------------------------------------------------------------------------

const qaBhausahebEn: QAAnswer = {
  kind: "qa",
  classification: "meta",
  question: "Who was Bhausaheb Maharaj?",
  framing:
    "Bhausaheb Maharaj was a 19th-century saint of the Nimbal lineage and the guru of Shri Gurudev. He stands in the line descending from Nimbargi Maharaj, and his correspondence and oral teachings — preserved by close disciples — became a primary spiritual influence on Gurudev's namasadhana. He is remembered in the sampradaya for his emphasis on the Name and on a quiet, disciplined inwardness rather than public display.",
  citations: [],
  references: [
    {
      workTitle: "Bodhsudha",
      location: "biographical preface",
      author: "Nimbargi Maharaj",
    },
    {
      workTitle: "Pathway to God in Hindi Literature",
      location: "Author's note on lineage",
      author: "Shri Gurudev",
    },
  ],
};

const qaBhausahebMr: QAAnswer = {
  kind: "qa",
  classification: "meta",
  question: "भाऊसाहेब महाराज कोण होते?",
  framing:
    "भाऊसाहेब महाराज हे एकोणिसाव्या शतकातील निंबाळ संप्रदायाचे संत आणि श्री गुरुदेव रानडे यांचे सद्गुरू. निंबर्गी महाराजांच्या परंपरेत त्यांचे स्थान असून, त्यांचे पत्रव्यवहार व मौखिक शिकवण — जवळच्या शिष्यांनी जपून ठेवलेली — गुरुदेवांच्या नामसाधनेवर मूलभूत प्रभाव टाकणारी ठरली. सार्वजनिक प्रसिद्धीपेक्षा नाम आणि शांत, शिस्तबद्ध अंतर्मुखतेवर त्यांचा भर असे, अशी त्यांची संप्रदायातील आठवण आहे.",
  citations: [],
  references: [
    {
      workTitle: "बोधसुधा",
      location: "चरित्रात्मक प्रस्तावना",
      author: "निंबर्गी महाराज",
    },
    {
      workTitle: "Pathway to God in Hindi Literature",
      location: "लेखकाची परंपरेविषयीची टीप",
      author: "श्री गुरुदेव रानडे",
    },
  ],
};

// ---------------------------------------------------------------------------
// 3. Pravachan — Adhyay 12 + Gurudev's life.
//    Structure is illustrative; athvani text is placeholder.
//    Per-language variants so the chat page stays language-blind.
// ---------------------------------------------------------------------------

const pravachanAdhyay12En: PravachanAnswer = {
  kind: "pravachan",
  question:
    "Share some athvanis corresponding to Adhyay 12 of the Geeta and how it relates to Gurudev's life.",
  thesis:
    "Adhyay 12 of the Gita lays out bhakti as the highest yoga; Shri Gurudev's life embodies that teaching through unbroken namasadhana, reverence for the spiritual Teacher, and a quiet preference for service over display.",
  gurudevsWords: {
    body:
      "Mysticism denotes that attitude of mind which involves a direct, immediate, intuitive apprehension of God. It signifies the highest attitude of which man is capable, namely, a beatific contemplation of God, and its dissemination in the Society and the World.",
    workTitle: "Pathway to God in Hindi Literature",
    location: "General Introduction",
    kind: "canonical",
    author: "Shri Gurudev",
  },
  examples: [
    {
      title: "The trunks of Bhausaheb Maharaj's letters",
      // MOCK: replace with real athvani retrieval
      quote: {
        body:
          "ती. बाबांच्या पत्रांच्या पेट्या अत्यंत काळजीपूर्वक जपल्या जात... कुठल्याही प्रवासाला गेले तरी श्रीमहाराजांच्या पत्रव्यवहाराच्या पेट्या त्यांच्या समवेत असायच्याच!",
        workTitle: "निंबाळचे जुने घर",
        location: "जैसी गंगा वाहे, pp. 17-19",
        kind: "athvani",
        author: "Vijaya Apte (narrator)",
      },
      whyThisExample:
        "Shows bhakti-toward-guru as a daily devotional practice carried into every detail — not a metaphor but a way of moving through the world.",
      readSlug: "athvan-bhausaheb-letters",
    },
    {
      title: "Allahabad mornings",
      // MOCK: replace with real athvani retrieval
      quote: {
        body:
          "Long before sunrise the lamp was already on and the Name continuous beneath whatever philosophical work lay open on the desk.",
        workTitle: "Allahabad days",
        location: "athvani collection",
        kind: "athvani",
        author: "V.H. Date (narrator)",
      },
      whyThisExample:
        "Illustrates sustained namasadhana — the disciplined daily side of bhakti, not its emotional crest.",
      readSlug: "athvan-allahabad-mornings",
    },
    {
      title: "The Dharwad-University library donation",
      // MOCK: replace with real athvani retrieval
      quote: {
        body:
          "His personal collection — nearly two thousand volumes — was given to the university so that the next generation of seekers would have what he himself had assembled.",
        workTitle: "Dharwad bequest",
        location: "athvani collection",
        kind: "athvani",
        author: "compiler (narrator)",
      },
      readSlug: "athvan-dharwad-donation",
      whyThisExample:
        "Closes the arc — bhakti turned outward as service to the next generation; a good final image for a pravachan.",
    },
  ],
};

const pravachanAdhyay12Mr: PravachanAnswer = {
  kind: "pravachan",
  question:
    "गीतेच्या १२व्या अध्यायावर प्रवचनासाठी साहित्य",
  thesis:
    "गीतेच्या बाराव्या अध्यायात भक्ती ही सर्वोच्च योग म्हणून मांडली आहे; श्री गुरुदेवांचे जीवन त्या शिकवणीचेच मूर्तिमंत स्वरूप — अखंड नामसाधना, सद्गुरूविषयीची दृढ श्रद्धा, आणि प्रसिद्धीपेक्षा सेवेला दिलेले महत्त्व.",
  gurudevsWords: {
    // Quote body stays in original language (ADR-007); thesis + section
    // labels render in the user's language.
    body:
      "Mysticism denotes that attitude of mind which involves a direct, immediate, intuitive apprehension of God. It signifies the highest attitude of which man is capable, namely, a beatific contemplation of God, and its dissemination in the Society and the World.",
    workTitle: "Pathway to God in Hindi Literature",
    location: "General Introduction",
    kind: "canonical",
    author: "Shri Gurudev",
  },
  examples: [
    {
      title: "ती. भाऊसाहेब महाराजांच्या पत्रांच्या पेट्या",
      quote: {
        body:
          "ती. बाबांच्या पत्रांच्या पेट्या अत्यंत काळजीपूर्वक जपल्या जात... कुठल्याही प्रवासाला गेले तरी श्रीमहाराजांच्या पत्रव्यवहाराच्या पेट्या त्यांच्या समवेत असायच्याच!",
        workTitle: "निंबाळचे जुने घर",
        location: "जैसी गंगा वाहे, pp. 17-19",
        kind: "athvani",
        author: "Vijaya Apte (narrator)",
      },
      whyThisExample:
        "गुरूविषयीची भक्ती ही केवळ रूपक नसून प्रत्येक तपशिलात उतरलेली रोजची साधना आहे — हे या आठवणीतून दिसते.",
      readSlug: "athvan-bhausaheb-letters",
    },
    {
      title: "अलाहाबादच्या सकाळी",
      quote: {
        body:
          "Long before sunrise the lamp was already on and the Name continuous beneath whatever philosophical work lay open on the desk.",
        workTitle: "Allahabad days",
        location: "athvani collection",
        kind: "athvani",
        author: "V.H. Date (narrator)",
      },
      whyThisExample:
        "नामसाधनेची शिस्तबद्ध, दैनंदिन बाजू अधोरेखित होते — भक्तीचे भावोत्कट शिखर नव्हे, तर तिचा टिकाऊ पाया.",
      readSlug: "athvan-allahabad-mornings",
    },
    {
      title: "धारवाड विद्यापीठाला दिलेले ग्रंथदान",
      quote: {
        body:
          "His personal collection — nearly two thousand volumes — was given to the university so that the next generation of seekers would have what he himself had assembled.",
        workTitle: "Dharwad bequest",
        location: "athvani collection",
        kind: "athvani",
        author: "compiler (narrator)",
      },
      readSlug: "athvan-dharwad-donation",
      whyThisExample:
        "भक्ती शेवटी सेवेत रूपांतरित होते — पुढच्या पिढीसाठी जे गोळा केले ते सगळे देऊन टाकणे, हीच भक्तीची परिणती.",
    },
  ],
};

// ---------------------------------------------------------------------------
// 4. Reading — Pathway to God in Hindi Literature, opening of the General
//    Introduction (the "Intuitional Character" stretch). Paragraphs are
//    verbatim from text.md; the slug below resolves these.
// ---------------------------------------------------------------------------

export type ReadingPage = {
  workSlug: string;
  workTitle: string;
  author: string;
  chapter: string;
  totalPages: number;
  paragraphs: { n: number; body: string }[];
};

const pghlReading: ReadingPage = {
  workSlug: "pathway-to-god-in-hindi-literature",
  workTitle: "Pathway to God in Hindi Literature",
  author: "Shri Gurudev",
  chapter: "General Introduction — Intuitional Character",
  totalPages: 18,
  paragraphs: [
    {
      n: 1,
      body:
        "Mysticism denotes that attitude of mind which involves a direct, immediate, intuitive apprehension of God. It signifies the highest attitude of which man is capable, namely, a beatific contemplation of God, and its dissemination in the Society and the World. The surest criterion of mysticism is the reality of the experience as enjoyed by the mystic himself. It is known only to him and to his Maker. Before it there is no appeal; for it there is no criterion. It is this personal-divine aspect of a mystic's spiritual realisation which stamps it with a peculiar halo and worth. It is in this sense that mystical experience has been regarded as ineffable.",
    },
    {
      n: 2,
      body:
        "It has been very often supposed that, for mystical experience, no separate faculty like intuition need be requisitioned, but that intellect, feeling, and will might suffice to enable us to have a full experience of God. Now it is a matter of common knowledge that even for heights to be reached in artistic, scientific, or poetic activity, a certain amount of direct, immediate, intuitive contact with Reality is required. Far more is this the case in the matter of mystical experience. Intuition, far from contradicting intelligence, feeling, or will, does penetrate and lie at the back of them all.",
    },
    {
      n: 3,
      body:
        "Intuition would not deny to Mysticism a title to philosophy if intellect requires it. As it connotes a determinative effort towards the acquisition of reality, it implies a definite, prolonged, and continuous exercise of the will. As feeling brings the subject and object into more intimate contact than any other psychological process, it also becomes a vital part of the process of realisation. Thus it seems that intelligence, will, and feeling are all necessary in the case of mystical endeavour. Only intuition must back them all. It is this unique character of mystical experience, namely, its intuitive and ineffable character, which has served to make all God-aspiring humanity a common and hidden society, the laws of which are known to themselves, if at all.",
    },
  ],
};

// ---------------------------------------------------------------------------
// Resolver helpers consumed by the route handlers.
// ---------------------------------------------------------------------------

// Per-language conversation table. The API layer picks the variant by lang.
// Each id maps to {en, mr} variants — the chat page stays language-blind.
type ConversationVariants = { en: Conversation; mr: Conversation };

const conversations: Record<string, ConversationVariants> = {
  demo: {
    en: { id: "demo", defaultMode: "qa", answer: qaBhaktiEn },
    mr: { id: "demo", defaultMode: "qa", answer: qaBhaktiMr },
  },
  "meta-bhausaheb": {
    en: { id: "meta-bhausaheb", defaultMode: "qa", answer: qaBhausahebEn },
    mr: { id: "meta-bhausaheb", defaultMode: "qa", answer: qaBhausahebMr },
  },
  "pravachan-demo": {
    en: {
      id: "pravachan-demo",
      defaultMode: "pravachan",
      answer: pravachanAdhyay12En,
    },
    mr: {
      id: "pravachan-demo",
      defaultMode: "pravachan",
      answer: pravachanAdhyay12Mr,
    },
  },
};

export function getConversation(
  id: string,
  mode: "qa" | "pravachan" | "reading",
  lang: Lang = "en",
): Conversation {
  // The same demo id supports both Q&A and pravachan output — the mode picker
  // chooses which mock body to surface.
  if (mode === "pravachan") return conversations["pravachan-demo"][lang];
  const variants = conversations[id] ?? conversations["demo"];
  return variants[lang];
}

// Athvani-as-reading-page mocks. Each athvan opens to a single-page
// "reading" surface so the user can see the full story instead of just
// the excerpt that appeared in the Pravachan brief. Real implementation
// would pull these from the curated athvani collections in the corpus.
const athvanBhausahebLetters: ReadingPage = {
  workSlug: "athvan-bhausaheb-letters",
  workTitle: "The trunks of Bhausaheb Maharaj's letters",
  author: "Vijaya Apte (narrator)",
  chapter: "जैसी गंगा वाहे · pp. 17–19",
  totalPages: 1,
  paragraphs: [
    {
      n: 1,
      body:
        "ती. बाबांच्या पत्रांच्या पेट्या अत्यंत काळजीपूर्वक जपल्या जात. कोणत्याही प्रवासाला निघाले तरी श्रीमहाराजांच्या पत्रव्यवहाराच्या त्या पेट्या त्यांच्या समवेत असायच्याच — जणू त्या पेट्यांमध्ये केवळ कागद नव्हते, गुरूंचे शब्द जिवंत होते.",
    },
    {
      n: 2,
      body:
        "घरात इतर वस्तू कुठेही ठेवल्या जात, पण ती. बाबा त्या पेट्यांना स्वतःच्या हाताने उघडायचे, स्वतःच ठेवायचे, स्वतःच बंद करायचे. कोणत्याही नोकराला त्या पेट्यांना हात लावू देत नसत.",
    },
  ],
};

const athvanAllahabadMornings: ReadingPage = {
  workSlug: "athvan-allahabad-mornings",
  workTitle: "Allahabad mornings",
  author: "V.H. Date (narrator)",
  chapter: "Athvani collection",
  totalPages: 1,
  paragraphs: [
    {
      n: 1,
      body:
        "Long before sunrise the lamp was already on and the Name continuous beneath whatever philosophical work lay open on the desk. The first hour of the morning was for Gurudev's own sadhana — a discipline he never let teaching or correspondence displace.",
    },
    {
      n: 2,
      body:
        "Students who came early would find him already writing, but the writing was a thin layer above what was clearly the deeper current of namasadhana. When asked once how he kept the practice unbroken through such a busy academic life, he answered: \"The Name does not need much room. It only needs to be unbroken.\"",
    },
  ],
};

const athvanDharwadDonation: ReadingPage = {
  workSlug: "athvan-dharwad-donation",
  workTitle: "The Dharwad-University library donation",
  author: "Compiler (narrator)",
  chapter: "Athvani collection",
  totalPages: 1,
  paragraphs: [
    {
      n: 1,
      body:
        "His personal collection — nearly two thousand volumes accumulated over a lifetime of reading in five languages — was given to the university so that the next generation of seekers would have what he himself had assembled. He kept nothing back.",
    },
    {
      n: 2,
      body:
        "The donation was made quietly, without ceremony. When the university wanted to honor the gift with a public function, Gurudev declined: \"The books will do the honoring. Let them go to readers.\" A few volumes that had marginal notes in his hand were the only ones he allowed to be kept under glass.",
    },
  ],
};

// Marathi reading mock — same conceptual passages as PGHL but rendered in
// Marathi, so devotees in MR mode actually see a Marathi reading surface.
// Replace with proper chunked content from the corpus once ingestion of
// the Marathi works is complete.
const pgmlReading: ReadingPage = {
  workSlug: "pathway-to-god-in-marathi-literature",
  workTitle: "मराठी साहित्यातून परमेश्वर",
  author: "श्री गुरुदेव रानडे",
  chapter: "सर्वसामान्य प्रस्तावना — अंतर्ज्ञानात्मक स्वरूप",
  totalPages: 18,
  paragraphs: [
    {
      n: 1,
      body:
        "गूढवादाचा अर्थ असा की चित्ताची ती अवस्था जिच्यात ईश्वराची प्रत्यक्ष, तत्काळ, अंतर्ज्ञानात्मक अनुभूती असते. हा मनुष्याच्या सर्वोच्च क्षमतेचा अविष्कार आहे — ईश्वराचे आनंदमय चिंतन आणि त्याचा समाजात व जगात प्रसार. गूढ अनुभवाचे एकमेव प्रमाण म्हणजे गूढवाद्याला स्वतःला आलेली अनुभूती. ती फक्त त्यालाच आणि त्याच्या निर्मात्याला माहीत असते. तिच्यापुढे कोणतेही अपील नाही; तिच्यासाठी कोणताही निकष नाही.",
    },
    {
      n: 2,
      body:
        "बहुधा असे समजले जाते की गूढ अनुभवासाठी अंतर्ज्ञानासारख्या वेगळ्या क्षमतेची गरज नाही; बुद्धी, भावना आणि इच्छाशक्ती हीच पुरेशी असतात. परंतु प्रत्यक्ष आहे की कलात्मक, वैज्ञानिक किंवा काव्यात्मक उत्कर्षासाठीही वास्तवाशी प्रत्यक्ष, तत्काळ, अंतर्ज्ञानात्मक संपर्क आवश्यक असतो. गूढ अनुभवाच्या बाबतीत हे आणखी सत्य आहे. अंतर्ज्ञान बुद्धी, भावना किंवा इच्छेला विरोध करत नाही — ते त्यांच्या मुळाशी असून त्यांना व्यापून असते.",
    },
    {
      n: 3,
      body:
        "जर बुद्धीला आवश्यक वाटले तर अंतर्ज्ञान गूढवादाला तत्त्वज्ञानाची मान्यता नाकारत नाही. वास्तवाच्या प्राप्तीसाठी निश्चयी प्रयत्न यात अंतर्भूत असल्याने, ते इच्छाशक्तीचा निश्चित, दीर्घ आणि सातत्यपूर्ण व्यायाम सूचित करते. भावना ही विषय-वस्तूला कोणत्याही इतर मानसिक प्रक्रियेपेक्षा अधिक घनिष्ठ संपर्कात आणते, म्हणूनच ती अनुभूतीच्या प्रक्रियेचा अविभाज्य भाग बनते. अशा प्रकारे, गूढ साधनेत बुद्धी, इच्छा आणि भावना या सर्वांची आवश्यकता असते, परंतु अंतर्ज्ञान त्या सर्वांना आधार देणारे असले पाहिजे.",
    },
  ],
};

const readingPages: Record<string, ReadingPage> = {
  "pathway-to-god-in-hindi-literature": pghlReading,
  "pathway-to-god-in-marathi-literature": pgmlReading,
  "athvan-bhausaheb-letters": athvanBhausahebLetters,
  "athvan-allahabad-mornings": athvanAllahabadMornings,
  "athvan-dharwad-donation": athvanDharwadDonation,
};

export function getReadingPage(slug: string): ReadingPage | undefined {
  return readingPages[slug];
}

// Internal accessors used by the API route for routing requests to the
// right mock. Kept module-internal so consumers don't reach in directly.
export function getQaMeta(lang: Lang): QAAnswer {
  return lang === "mr" ? qaBhausahebMr : qaBhausahebEn;
}

export function getQaDoctrinal(lang: Lang): QAAnswer {
  return lang === "mr" ? qaBhaktiMr : qaBhaktiEn;
}

export function getPravachanMock(lang: Lang): PravachanAnswer {
  return lang === "mr" ? pravachanAdhyay12Mr : pravachanAdhyay12En;
}

export type ModeId = "qa" | "pravachan" | "reading";

// Reading-mode suggestions carry their own slug — each chip opens the work
// it advertises. Non-Reading suggestions just carry text. This replaces the
// previous `READING_SLUG: Record<Lang, string>` global on the landing page
// which routed all Reading chips to the same slug regardless of which chip
// was clicked.
export type Suggestion = { text: string; slug?: string };

// Fallback Reading slug per language — used when the user typed a custom
// Reading question that doesn't match any chip. TODO: real implementation
// is to let the user pick a work from a list rather than guess a default.
export const DEFAULT_READING_SLUG: Record<Lang, string> = {
  en: "pathway-to-god-in-hindi-literature",
  mr: "pathway-to-god-in-marathi-literature",
};

// Suggestions per mode AND language. Reading suggestions carry slugs so
// landing's submit() can route to the right work; Q&A and Pravachan
// suggestions are plain text (they become the question on the chat page).
export const SUGGESTIONS: Record<ModeId, Record<Lang, Suggestion[]>> = {
  qa: {
    en: [
      { text: "What are Gurudev’s views on Bhakti?" },
      { text: "Who was Bhausaheb Maharaj?" },
      { text: "What did Gurudev write about Kabir?" },
    ],
    mr: [
      { text: "श्री गुरुदेव भक्तीविषयी काय सांगतात?" },
      { text: "भाऊसाहेब महाराज कोण होते?" },
      { text: "गुरुदेवांनी कबीराविषयी काय लिहिले आहे?" },
    ],
  },
  pravachan: {
    en: [
      { text: "Stories about naam-sadhana" },
      { text: "Bhakti as taught by the Nimbal lineage" },
      { text: "Pravachan material on Bhagavad Geeta Chapter 12" },
    ],
    mr: [
      { text: "नामसाधनेवरील आठवणी" },
      { text: "निंबाळ संप्रदायातील भक्तीची शिकवण" },
      { text: "गीतेच्या १२व्या अध्यायावर प्रवचनासाठी साहित्य" },
    ],
  },
  reading: {
    en: [
      {
        text: "Open Pathway to God in Hindi Literature",
        slug: "pathway-to-god-in-hindi-literature",
      },
      {
        text: "Open Pathway to God in Marathi Literature",
        slug: "pathway-to-god-in-marathi-literature",
      },
      {
        // No real reading page for this yet — falls back at the landing layer
        // until ingestion lands. Keeping the chip in so the surface advertises
        // the eventual library; landing's submit() guards against missing slugs.
        text: "Bhajnamrut — opening verses",
        slug: "pathway-to-god-in-hindi-literature",
      },
    ],
    mr: [
      {
        text: "मराठी साहित्यातून परमेश्वर उघडा",
        slug: "pathway-to-god-in-marathi-literature",
      },
      {
        text: "हिंदी साहित्यातून परमेश्वर उघडा",
        slug: "pathway-to-god-in-hindi-literature",
      },
      {
        text: "भजनामृत — आरंभीचे श्लोक",
        slug: "pathway-to-god-in-marathi-literature",
      },
    ],
  },
};

export const MODES: { id: ModeId; label: string }[] = [
  { id: "qa", label: "Q&A" },
  { id: "pravachan", label: "Pravachan" },
  { id: "reading", label: "Reading" },
];
