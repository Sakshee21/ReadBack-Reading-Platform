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

ALICE_CHECKPOINT_QUESTIONS = [
    {
        "id": "q1",
        "type": "timeline",
        "prompt": "Which of these events happened first in the story?",
        "options": [
            "Alice attends the Mad Tea-Party",
            "Alice falls down the rabbit-hole",
            "Alice hears the Mock Turtle's story",
            "Alice joins the Queen's croquet game",
        ],
        "answer": "Alice falls down the rabbit-hole",
    },
    {
        "id": "q2",
        "type": "character",
        "prompt": "Who teaches Alice that eating a mushroom can change her size?",
        "options": ["The White Rabbit", "The Caterpillar", "The Cheshire Cat", "The Duchess"],
        "answer": "The Caterpillar",
    },
    {
        "id": "q3",
        "type": "inference",
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
        "type": "timeline",
        "prompt": "Which of these happens first?",
        "options": [
            "Mr. Bingley moves into Netherfield Park",
            "Elizabeth walks to Netherfield to nurse a sick Jane",
            "Mr. Collins proposes to Elizabeth",
            "Mr. Darcy first proposes to Elizabeth",
        ],
        "answer": "Mr. Bingley moves into Netherfield Park",
    },
    {
        "id": "q2",
        "type": "character",
        "prompt": "How is Mr. Collins related to the Bennet family?",
        "options": [
            "Mrs. Bennet's brother",
            "Mr. Bennet's cousin and heir to Longbourn",
            "Jane's fiancé",
            "Mr. Darcy's uncle",
        ],
        "answer": "Mr. Bennet's cousin and heir to Longbourn",
    },
    {
        "id": "q3",
        "type": "inference",
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
        "type": "timeline",
        "prompt": "Which of these happens first?",
        "options": [
            "Tom tricks other boys into whitewashing the fence for him",
            "Tom and Huck witness Injun Joe kill Doc Robinson in the graveyard",
            "Tom runs away to Jackson's Island",
            "Tom is nearly caught by Injun Joe in the courtroom",
        ],
        "answer": "Tom tricks other boys into whitewashing the fence for him",
    },
    {
        "id": "q2",
        "type": "character",
        "prompt": "Who is Tom's partner in mischief who lives outside conventional society?",
        "options": ["Sid", "Huckleberry Finn", "Joe Harper", "Ben Rogers"],
        "answer": "Huckleberry Finn",
    },
    {
        "id": "q3",
        "type": "inference",
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
        "type": "timeline",
        "prompt": "Which of these happens first?",
        "options": [
            "Victor Frankenstein creates and animates his creature",
            "The creature murders William",
            "Victor marries Elizabeth",
            "The creature demands that Victor create him a companion",
        ],
        "answer": "Victor Frankenstein creates and animates his creature",
    },
    {
        "id": "q2",
        "type": "character",
        "prompt": "Who narrates the outer frame of the novel, encountering Victor in the Arctic?",
        "options": ["Henry Clerval", "Robert Walton", "Alphonse Frankenstein", "Victor's creature"],
        "answer": "Robert Walton",
    },
    {
        "id": "q3",
        "type": "inference",
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

SEED_BOOKS = [
    {
        "gutenberg_id": 1952,
        "chapter_summaries": YELLOW_WALLPAPER_SUMMARIES,
        "checkpoints": [],
    },
    {
        "gutenberg_id": 11,
        "chapter_summaries": ALICE_SUMMARIES,
        "checkpoints": [{"chapter_index_trigger": 9, "questions": ALICE_CHECKPOINT_QUESTIONS}],
    },
    {
        "gutenberg_id": 74,
        "chapter_summaries": {},
        "checkpoints": [{"chapter_index_trigger": 9, "questions": TOM_SAWYER_CHECKPOINT_QUESTIONS}],
    },
    {
        "gutenberg_id": 84,
        "chapter_summaries": {},
        "checkpoints": [{"chapter_index_trigger": 5, "questions": FRANKENSTEIN_CHECKPOINT_QUESTIONS}],
    },
    {
        "gutenberg_id": 1342,
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
            for checkpoint_data in entry["checkpoints"]:
                existing = (
                    db.query(ComprehensionCheckpoint)
                    .filter(
                        ComprehensionCheckpoint.book_id == book.id,
                        ComprehensionCheckpoint.chapter_index_trigger
                        == checkpoint_data["chapter_index_trigger"],
                    )
                    .first()
                )
                if existing:
                    continue
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
