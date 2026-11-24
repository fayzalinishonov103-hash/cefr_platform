"""Placement test questions: 5 levels x 5 multiple-choice questions (grammar and vocabulary).

Each question: text, options, answer = index of the correct option in `options`.
The browser never sees `answer`; options are shuffled on every page load and the form sends the ORIGINAL index.
"""
LEVELS = ["A1", "A2", "B1", "B2", "C1"]


def _q(level, text, options, answer):
    return {"level": level, "text": text, "options": options, "answer": answer}


QUESTIONS = [
    # ---- A1
    _q("A1", "She ___ a student.", ["is", "are", "am"], 0),
    _q("A1", "I ___ from Uzbekistan.", ["is", "am", "are"], 1),
    _q("A1", "There ___ two books on the table.", ["is", "are", "be"], 1),
    _q("A1", "What is the opposite of “big”?", ["small", "tall", "long"], 0),
    _q("A1", "___ name is Ali.", ["I", "Me", "My"], 2),
    # ---- A2
    _q("A2", "Yesterday I ___ to the market.", ["go", "went", "goes"], 1),
    _q("A2", "She doesn’t ___ coffee.", ["drink", "drinks", "drinking"], 0),
    _q("A2", "My brother is ___ than me.", ["tall", "taller", "tallest"], 1),
    _q("A2", "We ___ watching TV now.", ["is", "do", "are"], 2),
    _q("A2", "There isn’t ___ milk in the fridge.", ["some", "any", "many"], 1),
    # ---- B1
    _q("B1", "If it rains tomorrow, we ___ at home.", ["would stay", "will stay", "stayed"], 1),
    _q("B1", "I have lived here ___ 2015.", ["for", "since", "from"], 1),
    _q("B1", "The film was so boring that I nearly ___ asleep.", ["fell", "fall", "falling"], 0),
    _q("B1", "This is the man ___ car was stolen.", ["who", "whose", "which"], 1),
    _q("B1", "You ___ wear a seat belt. It’s the law.", ["might", "can", "must"], 2),
    # ---- B2
    _q("B2", "If I had known about the problem, I ___ you earlier.", ["would tell", "would have told", "will tell"], 1),
    _q("B2", "By next year, she ___ her degree.", ["will finish", "finishes", "will have finished"], 2),
    _q("B2", "He denied ___ the window.", ["to break", "breaking", "break"], 1),
    _q("B2", "The meeting has been ___ until next week.", ["put off", "put away", "put up"], 0),
    _q("B2", "Hardly ___ the house when it started to rain.", ["she had left", "had she left", "she left"], 1),
    # ---- C1
    _q("C1", "His speech was so ___ that nobody could disagree with it.", ["compelling", "compulsory", "compelled"], 0),
    _q("C1", "I’d rather you ___ smoke in here.", ["don’t", "didn’t", "won’t"], 1),
    _q("C1", "It’s high time we ___ a decision.", ["make", "will make", "made"], 2),
    _q("C1", "The new policy has been met with widespread ___ among employees.", ["resent", "resentment", "resented"], 1),
    _q("C1", "Only after the results came out ___ the scale of the problem.", ["we realised", "did we realise", "we did realise"], 1),
]
