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


def seed_mock_test_2():
    title = "CEFR Reading Mock Test 2 (Multilevel)"
    if Test.query.filter_by(title=title).first():
        print("Mock Test 2 already exists - skipping.")
        return

    p1 = """Konigil paper mill is located eight kilometres from the ancient city of Samarkand. It was established by two brothers who wanted to revive the traditional method of making Samarkand paper, famous throughout the Islamic world for more than a thousand years.

The process uses the bark of the mulberry tree. Workers collect the branches in autumn, peel off the outer skin and boil the inner bark in a large pot for several hours. The softened fibres are then placed under a wooden hammer driven by a water wheel on the Siab river.

After beating for ten hours, the pulp is dissolved in water and filtered through a fine silk screen. The wet sheets are dried under heavy stones and polished with a smooth agate stone until they shine. Today, thousands of international tourists visit the mill every year to buy handmade notebooks and calligraphy sheets."""

    p2 = """A. Cambridge English Academy. Offers full-time preparation for Multilevel and IELTS exams. Classes are held Monday to Friday, 09:00 to 12:30. Every student receives a weekly one-on-one session with a certified native speaker examiner. Weekly full mock tests with computerized grading are included. Monthly tuition: 850,000 UZS.

B. Lexicon Flexi-Learn. Designed for busy university students and working professionals. Access video lectures 24/7 on our mobile app. Submit up to three essays per week for detailed line-by-line feedback from an instructor within 12 hours. Group speaking clubs meet every Saturday afternoon on Zoom. Monthly tuition: 250,000 UZS.

C. Polytechnic ESP Centre. Focuses on English for Science, Technology and Engineering. Students learn academic writing, data interpretation and presentation skills. Perfect for researchers planning to publish articles in international journals. Classes meet Tuesday and Thursday evenings from 18:30 to 20:30. Monthly tuition: 500,000 UZS.

D. FastTrack Intensive Bootcamp. A rigorous four-week crash course for candidates who have an upcoming exam within a month. Daily four-hour training sessions with non-stop practice on past exam papers, vocabulary drills and real-time speaking interviews. High-speed progress guaranteed. Monthly tuition: 950,000 UZS."""

    p3 = """I. Sunlight is one of the most abundant resources in desert and semi-arid regions. However, standard photovoltaic solar panels face significant efficiency losses when ambient temperatures rise above twenty-five degrees Celsius. For every additional degree of heat, typical solar cells lose approximately zero point four percent of their electrical output.

II. Dust and airborne sand pose an even greater challenge. In dry climates, a single dust storm can coat panel surfaces with fine particles, reducing sunlight absorption by as much as seventy percent in a matter of hours. Cleaning these installations requires substantial quantities of water, which is precisely the resource that arid regions lack.

III. In response, international engineers have developed waterless cleaning robots that travel along rows of panels at night. These devices use soft microfibre brushes combined with controlled electrostatic charges to sweep away dust without scratching the glass or consuming a single drop of liquid.

IV. Another promising innovation involves bi-facial solar panels mounted on reflective white gravel. Unlike conventional systems that only capture light from above, these panels generate electricity from both sides by utilizing sunlight reflected from the desert floor. This technique increases total energy harvest by up to twenty-five percent.

V. Furthermore, agricultural scientists are pioneering agrivoltaics: raising solar arrays several metres above the ground to grow drought-resistant crops such as saffron, lavender and date palms underneath the shade of the panels. The crops benefit from reduced evaporation, while water evaporating from the plants cools the panels from below, boosting their electrical output.

VI. Governments across Central Asia and the Middle East are now investing heavily in these hybrid technologies. By combining electricity generation with sustainable agriculture, arid countries hope to achieve both energy independence and food security in the face of a changing climate."""

    p4 = """Sleep was once considered a passive state during which both the brain and the body simply rested. Over the past three decades, however, neuroscientists have discovered that deep sleep is an active and critical period of neurological maintenance. During slow-wave sleep, the brain replays and consolidates memories gathered during waking hours, transferring information from the temporary storage of the hippocampus into the permanent architecture of the neocortex.

Research demonstrates that students who sleep eight hours after studying retain up to forty percent more vocabulary than those who stay awake all night cramming. During deep sleep, the brain also activates the glymphatic system—a biological waste-clearance network that flushes out metabolic toxins, including beta-amyloid proteins associated with cognitive decline.

Despite these proven benefits, global surveys indicate that teenagers and young adults are experiencing chronic sleep deprivation, primarily driven by late-night smartphone usage. The blue light emitted by mobile screens suppresses the production of melatonin, the hormone that signals to the body that it is time to sleep."""

    p5 = """Biophilic architecture—the practice of incorporating nature and natural patterns into the built environment—is rapidly transforming contemporary city planning. For decades, modern urban design prioritized concrete, steel and utilitarian glass boxes, creating environments that evolutionary psychologists argue are fundamentally alien to the human nervous system. Studies consistently show that workers in windowless offices report higher levels of cortisol, increased absenteeism and reduced problem-solving ability compared to counterparts with views of greenery and sky.

Rather than treating plants and green spaces merely as decorative afterthoughts, biophilic architects integrate living elements directly into structural designs. Examples range from vertical forests—residential skyscrapers cloaked in thousands of trees and shrubs—to internal atriums with natural airflow, daylight illumination and water features.

While critics initially dismissed such projects as expensive marketing gimmicks, economic data now supports the biophilic approach. Buildings featuring natural elements achieve significantly higher rental premiums, lower employee turnover rates and reduced energy expenditure due to natural insulation. Most importantly, biophilic design reconnects urban populations with natural rhythms, proving that technological advancement and human biological wellbeing can coexist in modern megacities."""

    courses2 = [["A", "Cambridge English Academy"], ["B", "Lexicon Flexi-Learn"],
                 ["C", "Polytechnic ESP Centre"], ["D", "FastTrack Intensive Bootcamp"]]

    headings2 = [
        ["A", "The threat of dust and water scarcity"],
        ["B", "Why hot temperatures reduce solar efficiency"],
        ["C", "High costs prevent widespread adoption"],
        ["D", "Night-time robotic cleaning solutions"],
        ["E", "Combining solar power with crop farming"],
        ["F", "Double-sided panels that catch reflected light"],
        ["G", "National strategies for future energy and food"],
        ["H", "How clouds damage solar installations"]
    ]

    parts = [
        (1, "Part 1 · Gap fill (Konigil Paper Mill)", p1, [("gap_fill", "Write ONE WORD or NUMBER from the text in each gap.", [
            (1, "The Konigil paper mill is situated ___ kilometres from Samarkand.", None, "eight|8", "A2"),
            (2, "The papermakers use the bark of the ___ tree.", None, "mulberry", "B1"),
            (3, "The branches are harvested by workers during the ___ season.", None, "autumn|fall", "B1"),
            (4, "The water wheel that beats the pulp is powered by the Siab ___.", None, "river", "A2"),
            (5, "Pulp is filtered using a fine screen made of ___.", None, "silk", "B1"),
            (6, "The dried paper sheets are polished with a smooth ___ stone.", None, "agate", "B2")])]),

        (2, "Part 2 · Matching Information (Courses)", p2, [("match", "Which academy matches each description? Choose A, B, C or D.", [
            (7, "Which course provides feedback on written essays within twelve hours?", courses2, "B", "B1"),
            (8, "Which course includes a weekly private session with a native examiner?", courses2, "A", "B2"),
            (9, "Which course is specially created for engineers and scientists?", courses2, "C", "B1"),
            (10, "Which course offers Saturday afternoon speaking clubs on Zoom?", courses2, "B", "B1"),
            (11, "Which course is a rapid four-week preparation for imminent exams?", courses2, "D", "B2"),
            (12, "Which course has evening sessions on Tuesdays and Thursdays?", courses2, "C", "B1"),
            (13, "Which course has the highest tuition fee?", courses2, "D", "B1"),
            (14, "Which course holds classes every weekday morning?", courses2, "A", "B1")])]),

        (3, "Part 3 · Matching Headings (Solar Innovations)", p3, [("heading", "Choose the correct heading for each paragraph (I - VI).", [
            (15, "Paragraph I", headings2, "B", "B2"),
            (16, "Paragraph II", headings2, "A", "B2"),
            (17, "Paragraph III", headings2, "D", "B2"),
            (18, "Paragraph IV", headings2, "F", "B2"),
            (19, "Paragraph V", headings2, "E", "B2"),
            (20, "Paragraph VI", headings2, "G", "C1")])]),

        (4, "Part 4 · Multiple Choice & T/F/NG (The Science of Sleep)", p4, [
            ("mcq", "Choose the correct answer based on the text.", [
                (21, "Where does the brain permanently store consolidated memories?", abc("In the hippocampus", "In the neocortex", "In the optic nerve"), "b", "B2"),
                (22, "According to research, students who sleep 8 hours retain...", abc("40% more vocabulary than sleep-deprived students.", "40% less information.", "the exact same amount as crammers."), "a", "B2"),
                (23, "What is the primary function of the glymphatic system?", abc("To generate dreams", "To produce melatonin", "To clear metabolic toxins from brain tissue"), "c", "C1"),
                (24, "Why does screen blue light prevent sleep?", abc("It strains the optic muscles", "It stops melatonin secretion", "It increases body temperature"), "b", "B2")]),
            ("tfng", "Do the statements agree with the text? True, False or Not Given.", [
                (25, "Sleep was historically viewed as an active mental process.", TFNG, "false", "B2"),
                (26, "Students who cram all night perform better on long-term tests.", TFNG, "false", "B2"),
                (27, "Beta-amyloid toxins are linked to neurodegenerative disorders.", TFNG, "true", "C1"),
                (28, "Smartphones are banned in schools across Europe.", TFNG, "ng", "B2"),
                (29, "Melatonin helps inform the body that it is time to rest.", TFNG, "true", "B2")])]),

        (5, "Part 5 · Multiple Choice (Biophilic Urban Architecture)", p5, [("mcq", "Choose the correct option.", [
            (30, "What was a defining characteristic of mid-20th century architecture?", abc("Integration of trees and waterfalls", "Utilitarian steel, concrete and glass boxes", "Curved wooden structures"), "b", "C1"),
            (31, "What symptom is commonly observed among employees in windowless offices?", abc("Elevated cortisol levels and absenteeism", "Excessive productivity", "Lower blood pressure"), "a", "C1"),
            (32, "How do biophilic architects treat plant life?", abc("As cheap temporary decorations", "As structural, integrated functional components", "As an unnecessary burden"), "b", "C1"),
            (33, "What did critics initially say about biophilic buildings?", abc("They were too dark inside", "They were expensive marketing gimmicks", "They would attract dangerous insects"), "b", "C1"),
            (34, "What economic advantage has biophilic design demonstrated?", abc("Lower insurance costs only", "Higher rental premiums and lower staff turnover", "Government tax exemptions"), "b", "C1"),
            (35, "What is the primary message of the author?", abc("Cities should abandon modern technology entirely", "Nature and modern urban technology can be united for human wellbeing", "Office workers should all work remotely"), "b", "C1")])]),
    ]

    test = Test(title=title, skill="reading", duration_min=60)
    for number, part_title, passage, groups in parts:
        part = Part(number=number, title=part_title, passage=passage)
        for order, (qtype, instruction, questions) in enumerate(groups):
            group = QuestionGroup(order=order, qtype=qtype, instruction=instruction)
            for n, text, options, answer, level in questions:
                group.questions.append(Question(number=n, text=text, options=options, answer=answer, cefr_level=level))
            part.groups.append(group)
        test.parts.append(part)
    db.session.add(test)
    db.session.commit()
    print("CEFR Reading Mock Test 2 added: 5 parts, 35 questions.")


def seed_extra_prompts():
    new_writing = [
        ("essay", "Artificial Intelligence in Education",
         "Some people believe that artificial intelligence will eventually replace human teachers in schools and universities. Others argue that human interaction is essential for true education.\n\nDiscuss both views and give your own opinion. Write at least 150 words.",
         150, 300, 40),
        ("formal_letter", "Letter of Complaint to a Conference Organizer",
         "You recently attended an international student conference in Tashkent, but you were dissatisfied with the venue facilities and accommodation.\n\nWrite a formal letter to the organizer explaining the problems and requesting a partial refund. Write 100-150 words.",
         100, 180, 20),
    ]
    for task_type, title, prompt, min_w, max_w, mins in new_writing:
        if not WritingPrompt.query.filter_by(title=title).first():
            db.session.add(WritingPrompt(task_type=task_type, title=title, prompt=prompt, min_words=min_w, max_words=max_w, minutes=mins))

    new_speaking = [
        (1, "Hometown and Culture", 15, 45,
         "Answer these questions:\n- Can you describe your hometown or city?\n- What historical place or tradition are you most proud of?\n- How has your city changed over the past five years?"),
        (2, "A Book or Movie That Influenced You", 45, 90,
         "Describe a book, film or article that made a strong impression on you. You should say:\n- what it was\n- when you experienced it\n- what message or lesson it contained\nand explain why it influenced your thinking."),
        (3, "Environmental Responsibility", 30, 90,
         "Should environmental protection be primarily the responsibility of individual citizens, or should governments impose strict mandatory regulations on businesses?\nDiscuss your perspective with examples."),
    ]
    for part, title, think, speak, prompt in new_speaking:
        if not SpeakingPrompt.query.filter_by(title=title).first():
            db.session.add(SpeakingPrompt(part=part, title=title, think_seconds=think, speak_seconds=speak, prompt=prompt))
    db.session.commit()
    print("Extra Writing and Speaking prompts added.")


if __name__ == "__main__":
    with create_app().app_context():
        seed()
        seed_mock_test_2()
        seed_extra_prompts()
        seed_writing()
        seed_listening()
        seed_speaking()
