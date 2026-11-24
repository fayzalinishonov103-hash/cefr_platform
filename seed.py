"""Insert an ORIGINAL demo Reading test (5 parts, 35 questions). Run: python seed.py"""
from app import create_app
from extensions import db
from models import Test, Part, QuestionGroup, Question, WritingPrompt, SpeakingPrompt

TITLE = "Reading Demo Test 1"

COURSES = [["A", "Evening English Conversation"], ["B", "Intensive Exam Preparation"],
           ["C", "Online Self-Study Club"], ["D", "Weekend Business English"]]
HEADINGS = [["A", "Benefits for mental health"], ["B", "Obstacles that gardeners face"],
            ["C", "Why vegetables cost more in cities"], ["D", "A new way for neighbours to meet"],
            ["E", "Official help from local authorities"], ["F", "Green spaces appear in unexpected places"],
            ["G", "Plans for the future"], ["H", "Dangers of eating homegrown food"]]
TFNG = [["true", "True"], ["false", "False"], ["ng", "Not Given"]]


def abc(*texts):
    return [[v, t] for v, t in zip("abc", texts)]


P1 = """Last Saturday my family visited Lake Mavi. We left home at seven in the morning and drove for two hours. My father rented a small boat, and we sailed across the water to a green island.

The island has a quiet beach with soft sand. My little brother found a shiny shell there, and my sister painted the trees with her new colours. At noon we had a picnic under a big tree. Mother brought sandwiches, apples and cold tea.

In the afternoon we swam for an hour. We came home tired but very happy, and we are planning to go again in summer."""

P2 = """A. Evening English Conversation. Small groups of six meet on Tuesday and Thursday evenings from 18:30 to 20:00. Students practise speaking about everyday topics. There is no exam at the end. Price: 300,000 som per month.

B. Intensive Exam Preparation. Classes run five mornings a week, 9:00 to 12:00. There is a practice test every Friday and a final certificate exam. Teachers write feedback on every essay. Price: 700,000 som per month.

C. Online Self-Study Club. Study at any time using our app. There is a weekly video lesson, and a teacher answers questions by message within 24 hours. There is no fixed timetable. Price: 120,000 som per month.

D. Weekend Business English. Saturdays, 10:00 to 15:00, at our city centre office. Students learn how to write emails, take part in meetings and give presentations. Lunch is included. Price: 450,000 som per month."""

P3 = """In many big cities, empty roofs and unused corners are being turned into small gardens. Residents plant vegetables and flowers where once there was only concrete.

These gardens do more than produce food. Studies suggest that people who spend time among plants feel calmer and report lower stress at work.

Neighbours who never spoke before now share tools, seeds and advice. Many gardens organise weekly meetings, and older residents teach children how to grow tomatoes.

Not everything is easy. Water is expensive in dry cities, and the soil in some areas contains chemicals that must be tested before anything is planted.

Some city councils now support the idea. They lend empty land for a small fee and pay for courses that teach basic gardening skills.

Experts believe the trend will continue. New apartment blocks in several countries are already being designed with shared roof gardens from the start."""

P4 = """Ten years ago, many experts predicted that electronic readers would replace printed books within a generation. That has not happened. Sales of e-readers rose quickly at first but have been flat since 2015, while sales of paper books have grown slowly in most countries.

Researchers offer several explanations. Some studies show that people remember a story better when they read it on paper, perhaps because they can feel how far through the book they are. Others point out that a printed book makes a better gift and does not need charging.

Bookshops have also changed. Many now host readings and small cafés, so customers come for an experience, not only for a purchase. However, e-readers remain popular among travellers and among people with poor eyesight, who can make the letters larger. Young readers, surprisingly, are the group most loyal to print, and many say they already spend enough time on screens."""

P5 = """Economists have long assumed that more choice makes people better off. If we can pick from twenty kinds of jam rather than six, the logic goes, we are more likely to find the one we truly like. Yet a series of experiments has cast doubt on this assumption. In one well-known study, shoppers who were offered a large display of jams stopped to look more often than those who saw a small one, but they bought far less. The researchers concluded that an abundance of options can overwhelm people and make them postpone a decision altogether.

Later work added a further twist. Even when people do choose, those who faced many alternatives tend to be less satisfied afterwards, because they imagine the better outcome they may have missed. Psychologists call this anticipated regret. Some individuals, whom researchers label 'maximisers', insist on finding the single best option and suffer most. 'Satisficers', who accept anything that meets their needs, are generally happier.

Critics, however, urge caution. Several attempts to repeat the jam experiment failed to find the same effect, suggesting that it may depend on factors such as the type of product or whether shoppers already know what they want. The safest conclusion, they argue, is not that choice is harmful, but that its benefits flatten out beyond a certain point."""

# (qtype, instruction, [(number, text, options, answer, cefr_level)])
PARTS = [
 (1, "Gap fill", P1, [("gap_fill", "Write ONE WORD or NUMBER from the text in each gap.", [
    (1, "They left home at ___ in the morning.", None, "seven|7", "A2"),
    (2, "They crossed the water in a small ___.", None, "boat", "A2"),
    (3, "The island has a quiet beach with soft ___.", None, "sand", "A2"),
    (4, "The little brother found a shiny ___.", None, "shell", "A2"),
    (5, "At noon the family had a ___ under a big tree.", None, "picnic", "A2"),
    (6, "They want to visit the lake again in ___.", None, "summer", "A2")])]),
 (2, "Matching information", P2, [("match", "Which course...? Choose A, B, C or D. You may use a course more than once.", [
    (7, "Which course is the cheapest?", COURSES, "C", "B1"),
    (8, "Which course includes a meal?", COURSES, "D", "B1"),
    (9, "Which course ends with a certificate exam?", COURSES, "B", "B1"),
    (10, "Which course has no fixed timetable?", COURSES, "C", "B1"),
    (11, "Which course is held only in the evenings?", COURSES, "A", "B1"),
    (12, "Which course teaches students to give presentations?", COURSES, "D", "B1"),
    (13, "Which course has a practice test every week?", COURSES, "B", "B1"),
    (14, "Which course lets students send questions to a teacher?", COURSES, "C", "B1")])]),
 (3, "Matching headings", P3, [("heading", "Choose the correct heading for each paragraph. There are more headings than you need.", [
    (15, "Paragraph I", HEADINGS, "F", "B2"), (16, "Paragraph II", HEADINGS, "A", "B2"),
    (17, "Paragraph III", HEADINGS, "D", "B2"), (18, "Paragraph IV", HEADINGS, "B", "B2"),
    (19, "Paragraph V", HEADINGS, "E", "B2"), (20, "Paragraph VI", HEADINGS, "G", "B2")])]),
 (4, "Multiple choice and True / False / Not Given", P4, [
  ("mcq", "Choose the correct answer.", [
    (21, "What happened to e-reader sales after 2015?", abc("They kept rising quickly.", "They stopped growing.", "They fell sharply."), "b", "B2"),
    (22, "According to some studies, people who read on paper...", abc("enjoy stories less.", "finish books faster.", "remember stories better."), "c", "B2"),
    (23, "Why have many bookshops added cafés and readings?", abc("To sell more e-readers.", "To attract customers who want an experience.", "To lower book prices."), "b", "B2"),
    (24, "Why do some people with poor eyesight prefer e-readers?", abc("They need no charging.", "They are cheaper.", "The letters can be made larger."), "c", "B2")]),
  ("tfng", "Do the statements agree with the text?", [
    (25, "Experts once expected e-readers to replace paper books.", TFNG, "true", "B2"),
    (26, "Paper book sales have fallen in most countries.", TFNG, "false", "B2"),
    (27, "Travellers are the biggest group of e-reader buyers.", TFNG, "ng", "B2"),
    (28, "Many bookshops now offer events as well as books.", TFNG, "true", "B2"),
    (29, "Young readers say they want to spend more time on screens.", TFNG, "false", "B2")])]),
 (5, "Multiple choice", P5, [("mcq", "Choose the correct answer.", [
    (30, "What did the jam study find?", abc("Shoppers ignored the large display.", "Shoppers looked more at the large display but bought less.", "Shoppers bought more from the small display because it was cheaper."), "b", "C1"),
    (31, "What is 'anticipated regret'?", abc("Feeling sorry after a poor purchase.", "Refusing to buy because of earlier mistakes.", "Imagining a better option that may have been missed."), "c", "C1"),
    (32, "Which group is generally happier?", abc("Satisficers", "Maximisers", "Economists"), "a", "C1"),
    (33, "What happened when the jam experiment was repeated?", abc("It always gave the same result.", "It did not always give the same result.", "Nobody tried it."), "b", "C1"),
    (34, "What do the critics think is the safest conclusion?", abc("That choice is harmful.", "That shoppers should pick the cheapest item.", "That the benefits of choice level off beyond a point."), "c", "C1"),
    (35, "What is the main purpose of the text?", abc("To show that too much choice may reduce satisfaction, though the evidence is debated.", "To advise people how to shop.", "To prove that economists were right."), "a", "C1")])]),
]


def seed():
    if Test.query.filter_by(title=TITLE).first():
        print("Demo test already exists - nothing to do.")
        return
    test = Test(title=TITLE, skill="reading", duration_min=60)
    for number, title, passage, groups in PARTS:
        part = Part(number=number, title=title, passage=passage)
        for order, (qtype, instruction, questions) in enumerate(groups):
            group = QuestionGroup(order=order, qtype=qtype, instruction=instruction)
            for n, text, options, answer, level in questions:
                group.questions.append(Question(number=n, text=text, options=options, answer=answer, cefr_level=level))
            part.groups.append(group)
        test.parts.append(part)
    db.session.add(test)
    db.session.commit()
    print("Demo test added: 5 parts, 35 questions.")


WRITING = [
    ("informal_letter", "Letter to a friend who moved", 50, 80, 10,
     "Your friend has just moved to a new city. Write a letter to your friend. In your letter:\n- congratulate him or her on the move\n- tell your friend about something new in your own life\n- invite your friend to visit you."),
    ("formal_letter", "Complaint about a damaged laptop", 120, 150, 20,
     "Last week you bought a laptop from an online shop. It arrived damaged. Write a formal letter to the customer service manager. In your letter:\n- describe the problem\n- explain what you would like the shop to do\n- ask for a reply within seven days."),
    ("essay", "Foreign languages at primary school", 180, 220, 30,
     "Some people think children should start learning a foreign language at primary school. Others believe it is better to start in secondary school. Discuss both views and give your own opinion."),
]


def seed_writing():
    if WritingPrompt.query.count():
        print("Writing prompts already exist - nothing to do.")
        return
    for task_type, title, lo, hi, minutes, prompt in WRITING:
        db.session.add(WritingPrompt(task_type=task_type, title=title, prompt=prompt,
                                     min_words=lo, max_words=hi, minutes=minutes))
    db.session.commit()
    print(f"{len(WRITING)} writing prompts added.")


LISTENING_TITLE = "Listening demo test (audio kerak)"
LISTENING_PARTS = [
    (1, "Short conversations",
     "Man: Excuse me, does the number 14 bus go to the central station?\n\nWoman: No, you need the 41. It leaves from the stop across the road, every ten minutes.\n\nMan: Thank you. And how much is a ticket?\n\nWoman: Two thousand five hundred som, and you pay the driver.",
     [("gap_fill", "Complete the sentences. Write ONE WORD OR NUMBER.", [
         (1, "The man should take bus number ___.", None, "41|forty-one|forty one", "A2"),
         (2, "The bus leaves every ___ minutes.", None, "10|ten", "A2")]),
      ("mcq", "Choose the correct answer.", [
         (3, "Where does the bus leave from?", [["a", "The same side of the road"], ["b", "Across the road"], ["c", "The central station"]], "b", "A2"),
         (4, "How can the man pay?", [["a", "By card online"], ["b", "At the machine"], ["c", "To the driver"]], "c", "B1")])]),
    (2, "A talk about sleep",
     "Good evening everyone. Tonight I would like to talk about sleep. Many adults believe they can manage on five hours a night, but research suggests that most of us need between seven and nine. When we sleep too little, our memory gets worse and we make more mistakes.\n\nOne simple habit that helps is going to bed at the same time every day, even at weekends. Another is to avoid screens for an hour before bed, because the light from a phone tells the brain that it is still daytime.",
     [("tfng", "Write TRUE, FALSE or NOT GIVEN.", [
         (5, "Most adults need seven to nine hours of sleep.", TFNG, "true", "B1"),
         (6, "Weekend lie-ins are good for memory.", TFNG, "ng", "B2"),
         (7, "Light from a phone can make it harder to fall asleep.", TFNG, "true", "B2")]),
      ("mcq", "Choose the correct answer.", [
         (8, "What does the speaker recommend?", [["a", "Sleeping less at weekends"], ["b", "A regular bedtime"], ["c", "Using the phone as an alarm"]], "b", "B1")])]),
]


def seed_listening():
    """Demo Listening test WITHOUT audio, hidden until the admin uploads audio for each part."""
    if Test.query.filter_by(title=LISTENING_TITLE).first():
        print("Listening demo already exists - nothing to do.")
        return
    test = Test(title=LISTENING_TITLE, skill="listening", duration_min=20, is_active=False)
    for number, title, transcript, groups in LISTENING_PARTS:
        part = Part(number=number, title=title, passage=transcript)    # passage = transcript, shown after the test
        for order, (qtype, instruction, questions) in enumerate(groups):
            group = QuestionGroup(order=order, qtype=qtype, instruction=instruction)
            for n, text, options, answer, level in questions:
                group.questions.append(Question(number=n, text=text, options=options, answer=answer, cefr_level=level))
            part.groups.append(group)
        test.parts.append(part)
    db.session.add(test)
    db.session.commit()
    print("Listening demo added (hidden): 2 parts, 8 questions. Admin: upload audio for each part, then activate it.")


SPEAKING = [
    (1, "About your daily routine", 15, 40,
     "Answer these questions.\n- What time do you usually get up?\n- What do you like to do after work or school?\n- Do you prefer mornings or evenings? Why?"),
    (2, "Describe a place you like", 45, 90,
     "Describe a place in your city that you like to visit. You should say:\n- where it is\n- what you can see or do there\n- who you go with\nand explain why this place is special for you."),
    (3, "Technology and learning", 30, 90,
     "Some people think students learn better with tablets and apps than with paper books.\nDo you agree or disagree? Give reasons and examples."),
]


def seed_speaking():
    if SpeakingPrompt.query.count():
        print("Speaking prompts already exist - nothing to do.")
        return
    for part, title, think, speak, prompt in SPEAKING:
        db.session.add(SpeakingPrompt(part=part, title=title, think_seconds=think, speak_seconds=speak, prompt=prompt))
    db.session.commit()
    print(f"{len(SPEAKING)} speaking prompts added.")


if __name__ == "__main__":
    with create_app().app_context():
        seed()
        seed_writing()
        seed_listening()
        seed_speaking()
