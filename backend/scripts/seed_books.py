"""Seeds the database with 5 public-domain books plus hand-authored chapter
summaries (for the recap engine) and comprehension checkpoints for one
~10-chapter milestone per book.

Chapters without a hand-authored summary fall back to a deterministic
first-sentence extraction (see app.services.summarize.naive_summary) so the
recap engine still has something to work with - see SEED.md for the scope
note on this simplification.

Usage:
    python -m scripts.seed_books
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models import Book, ComprehensionCheckpoint  # noqa: E402
from scripts.import_book import import_book  # noqa: E402

ALICE_SUMMARIES = {
    0: "Alice follows a White Rabbit down a rabbit-hole and falls into a strange "
    "hall, where a potion shrinks her too small to reach the key to a tiny door.",
    1: "After crying an enormous pool of tears, Alice shrinks and swims through it "
    "with a mouse and other creatures she startled by talking about her cat.",
    2: "Alice and the animals hold a chaotic 'Caucus-race' to dry off, and the Dodo "
    "awards Alice her own thimble as a prize.",
    3: "The White Rabbit mistakes Alice for his housemaid; after growing giant-sized "
    "inside his house, she escapes and shrinks again in a wood.",
    4: "A hookah-smoking Caterpillar teaches Alice that eating different sides of a "
    "mushroom can make her grow or shrink.",
    5: "Alice enters the Duchess's chaotic kitchen, rescues a baby that turns into a "
    "pig, and meets the ever-grinning Cheshire Cat.",
    6: "At a never-ending Mad Tea-Party, Alice argues with the Hatter, the March "
    "Hare, and a sleepy Dormouse about time and riddles.",
    7: "Alice joins the Queen of Hearts's bizarre croquet game, played with "
    "flamingos and hedgehogs under constant threat of execution.",
    8: "The Duchess and the Gryphon take Alice to hear the melancholy Mock Turtle "
    "tell of his school days 'in the sea.'",
}

YELLOW_WALLPAPER_SUMMARIES = {
    0: "A woman confined to a room by her husband for a 'rest cure' becomes "
    "obsessed with the pattern in the room's yellow wallpaper, seeing a trapped "
    "woman within it who comes to mirror her own unraveling sanity.",
}

# Every question set below is spoiler-safe for its trigger chapter: it only
# refers to events the reader has already finished. See SEED.md.

ALICE_CHECKPOINT_QUESTIONS = [
    {
        "id": "q1",
        "question_type": "sequencing",
        "prompt": "Put these events in the order they happen.",
        "items": [
            "Alice argues with the Hatter at the Mad Tea-Party",
            "Alice follows the White Rabbit down the rabbit-hole",
            "The White Rabbit mistakes Alice for his housemaid Mary Ann",
            "Alice swims through the pool of her own tears",
        ],
        "answer": [
            "Alice follows the White Rabbit down the rabbit-hole",
            "Alice swims through the pool of her own tears",
            "The White Rabbit mistakes Alice for his housemaid Mary Ann",
            "Alice argues with the Hatter at the Mad Tea-Party",
        ],
    },
    {
        "id": "q2",
        "question_type": "relationship",
        "prompt": "Match each character to how Alice meets them.",
        "left_items": ["The Caterpillar", "The Cheshire Cat", "The Duchess", "The Queen of Hearts"],
        "options": [
            "Sits on a mushroom smoking a hookah",
            "Vanishes slowly until only a grin is left",
            "Nurses a baby that turns into a pig",
            "Calls for beheadings during the croquet game",
        ],
        "answer": {
            "The Caterpillar": "Sits on a mushroom smoking a hookah",
            "The Cheshire Cat": "Vanishes slowly until only a grin is left",
            "The Duchess": "Nurses a baby that turns into a pig",
            "The Queen of Hearts": "Calls for beheadings during the croquet game",
        },
    },
    {
        "id": "q3",
        "question_type": "inference",
        "prompt": "What does the Cheshire Cat's habit of slowly vanishing until only its "
        "grin remains suggest about Wonderland?",
        "options": [
            "Wonderland follows strict logical rules",
            "Wonderland's logic is dreamlike and defies normal physical rules",
            "The Cat is actually invisible the whole time",
            "The Cat is dying",
        ],
        "answer": "Wonderland's logic is dreamlike and defies normal physical rules",
    },
]

PRIDE_AND_PREJUDICE_CHECKPOINT_QUESTIONS = [
    {
        "id": "q1",
        "question_type": "sequencing",
        "prompt": "Put these events in the order they happen.",
        "items": [
            "Jane falls ill and Elizabeth walks to Netherfield to nurse her",
            "Mr. Bingley takes possession of Netherfield Park",
            "Mr. Collins arrives at Longbourn as the family's heir",
            "Mr. Darcy slights Elizabeth at the Meryton assembly",
        ],
        "answer": [
            "Mr. Bingley takes possession of Netherfield Park",
            "Mr. Darcy slights Elizabeth at the Meryton assembly",
            "Jane falls ill and Elizabeth walks to Netherfield to nurse her",
            "Mr. Collins arrives at Longbourn as the family's heir",
        ],
    },
    {
        "id": "q2",
        "question_type": "relationship",
        "prompt": "Match each character to their place in the story.",
        "left_items": ["Mr. Collins", "Mr. Bingley", "Charlotte Lucas", "Mrs. Bennet"],
        "options": [
            "The clergyman cousin who will inherit Longbourn",
            "The wealthy newcomer who rents Netherfield",
            "Elizabeth's closest friend in Meryton",
            "The mother determined to see her daughters married",
        ],
        "answer": {
            "Mr. Collins": "The clergyman cousin who will inherit Longbourn",
            "Mr. Bingley": "The wealthy newcomer who rents Netherfield",
            "Charlotte Lucas": "Elizabeth's closest friend in Meryton",
            "Mrs. Bennet": "The mother determined to see her daughters married",
        },
    },
    {
        "id": "q3",
        "question_type": "inference",
        "prompt": "Why does Mr. Darcy initially seem unpleasant to the Bennet family at "
        "the Meryton assembly?",
        "options": [
            "He openly insults their cooking",
            "He dances every dance enthusiastically",
            "He is aloof, dances with no one outside his own party, and is overheard "
            "calling Elizabeth 'not handsome enough'",
            "He proposes marriage to Elizabeth immediately",
        ],
        "answer": "He is aloof, dances with no one outside his own party, and is "
        "overheard calling Elizabeth 'not handsome enough'",
    },
]

TOM_SAWYER_CHECKPOINT_QUESTIONS = [
    {
        "id": "q1",
        "question_type": "sequencing",
        "prompt": "Put these events in the order they happen.",
        "items": [
            "Tom and Huck take a dead cat to the graveyard at midnight",
            "Tom tricks the other boys into whitewashing the fence for him",
            "Tom and Huck see Injun Joe kill Dr. Robinson",
            "Tom trades tickets for a Bible prize at Sunday school",
        ],
        "answer": [
            "Tom tricks the other boys into whitewashing the fence for him",
            "Tom trades tickets for a Bible prize at Sunday school",
            "Tom and Huck take a dead cat to the graveyard at midnight",
            "Tom and Huck see Injun Joe kill Dr. Robinson",
        ],
    },
    {
        "id": "q2",
        "question_type": "relationship",
        "prompt": "Match each character to their relationship to Tom.",
        "left_items": ["Aunt Polly", "Sid", "Huckleberry Finn", "Becky Thatcher"],
        "options": [
            "Tom's aunt and guardian",
            "Tom's well-behaved brother, who tells on him",
            "The outcast boy Tom roams with",
            "The judge's daughter Tom falls for",
        ],
        "answer": {
            "Aunt Polly": "Tom's aunt and guardian",
            "Sid": "Tom's well-behaved brother, who tells on him",
            "Huckleberry Finn": "The outcast boy Tom roams with",
            "Becky Thatcher": "The judge's daughter Tom falls for",
        },
    },
    {
        "id": "q3",
        "question_type": "inference",
        "prompt": "Why do Tom and Huck decide to keep silent about witnessing the murder?",
        "options": [
            "They didn't actually see anything",
            "They fear Injun Joe will kill them if they tell",
            "They think no one will believe two boys",
            "They want to solve the crime themselves for reward money",
        ],
        "answer": "They fear Injun Joe will kill them if they tell",
    },
]

FRANKENSTEIN_CHECKPOINT_QUESTIONS = [
    {
        "id": "q1",
        "question_type": "sequencing",
        "prompt": "Put these events in the order they happen.",
        "items": [
            "Victor brings his creature to life and flees in horror",
            "Robert Walton's ship finds Victor adrift on the ice",
            "Victor learns that his brother William has been murdered",
            "Victor leaves home to study at Ingolstadt",
        ],
        "answer": [
            "Robert Walton's ship finds Victor adrift on the ice",
            "Victor leaves home to study at Ingolstadt",
            "Victor brings his creature to life and flees in horror",
            "Victor learns that his brother William has been murdered",
        ],
    },
    {
        "id": "q2",
        "question_type": "relationship",
        "prompt": "Match each character to their role in the story so far.",
        "left_items": ["Robert Walton", "Henry Clerval", "Elizabeth Lavenza", "William Frankenstein"],
        "options": [
            "The Arctic explorer who narrates the outer frame",
            "Victor's closest friend, who nurses him through his illness",
            "Victor's beloved companion, raised alongside him in his family",
            "Victor's young brother, found murdered",
        ],
        "answer": {
            "Robert Walton": "The Arctic explorer who narrates the outer frame",
            "Henry Clerval": "Victor's closest friend, who nurses him through his illness",
            "Elizabeth Lavenza": "Victor's beloved companion, raised alongside him in his family",
            "William Frankenstein": "Victor's young brother, found murdered",
        },
    },
    {
        "id": "q3",
        "question_type": "inference",
        "prompt": "Why does Victor abandon his creature immediately after bringing it to life?",
        "options": [
            "He is called away on urgent business",
            "He is overcome with horror and disgust at its appearance",
            "The creature attacks him first",
            "He planned to study it later",
        ],
        "answer": "He is overcome with horror and disgust at its appearance",
    },
]

# Decorative mood tint per book - a background wash only, never scene imagery,
# so it can't compete with the reader's own mental picture. Theme names must
# exist in frontend/src/styles/themes.css (tests enforce this and WCAG AA).
SEED_BOOKS = [
    {
        "gutenberg_id": 1952,
        "theme": "faded",
        "chapter_summaries": YELLOW_WALLPAPER_SUMMARIES,
        "checkpoints": [],
    },
    {
        "gutenberg_id": 11,
        "theme": "meadow",
        "chapter_summaries": ALICE_SUMMARIES,
        "checkpoints": [{"chapter_index_trigger": 9, "questions": ALICE_CHECKPOINT_QUESTIONS}],
    },
    {
        "gutenberg_id": 74,
        "theme": "sunlit",
        "chapter_summaries": {},
        "checkpoints": [{"chapter_index_trigger": 9, "questions": TOM_SAWYER_CHECKPOINT_QUESTIONS}],
    },
    {
        "gutenberg_id": 84,
        "theme": "moonlit",
        "chapter_summaries": {},
        # Index 8 (not 5): chapter 0 is the framing letters, so index N is
        # Chapter N. Trigger 5 fired *before* the creature was animated in
        # Chapter 5, making its own questions spoilers. 8 means Letters plus
        # Chapters 1-7 are read - the creation and William's death included.
        "checkpoints": [{"chapter_index_trigger": 8, "questions": FRANKENSTEIN_CHECKPOINT_QUESTIONS}],
    },
    {
        "gutenberg_id": 1342,
        "theme": "rose",
        "chapter_summaries": {},
        # Index 15 (not 9) because chapter 0 here is front-matter (a preface),
        # shifting every real chapter's index up by one - and because the
        # Mr. Collins question below needs chapters 13-14 to have happened.
        "checkpoints": [
            {"chapter_index_trigger": 15, "questions": PRIDE_AND_PREJUDICE_CHECKPOINT_QUESTIONS}
        ],
    },
]


def seed():
    for entry in SEED_BOOKS:
        book_id = import_book(entry["gutenberg_id"], chapter_summaries=entry["chapter_summaries"])

        db = SessionLocal()
        try:
            book = db.get(Book, book_id)
            book.theme = entry["theme"]

            # Mark hand-authored chapters as 'manual' so the recap engine keeps
            # preferring them over any LLM recap. Done here (not only at import)
            # so books imported before recap_source existed get reconciled too.
            for chapter in book.chapters:
                if entry["chapter_summaries"].get(chapter.index) and chapter.recap_source != "manual":
                    chapter.recap_source = "manual"

            # Upsert rather than skip, so re-seeding an existing database picks
            # up edited questions and corrected trigger chapters. Checkpoint
            # rows are updated in place to keep past attempts referencing them.
            existing = (
                db.query(ComprehensionCheckpoint)
                .filter(ComprehensionCheckpoint.book_id == book.id)
                .order_by(ComprehensionCheckpoint.id)
                .all()
            )
            for i, checkpoint_data in enumerate(entry["checkpoints"]):
                if i < len(existing):
                    existing[i].chapter_index_trigger = checkpoint_data["chapter_index_trigger"]
                    existing[i].questions = checkpoint_data["questions"]
                else:
                    db.add(
                        ComprehensionCheckpoint(
                            book_id=book.id,
                            chapter_index_trigger=checkpoint_data["chapter_index_trigger"],
                            questions=checkpoint_data["questions"],
                        )
                    )
            db.commit()
        finally:
            db.close()

    print("Seeding complete.")


if __name__ == "__main__":
    seed()
