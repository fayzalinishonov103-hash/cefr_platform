"""Curated CEFR connected-speech dictation database (A2 to C1).
Zero AI cost: utilizes client/server Web Speech Synthesis and algorithmic word-diff.
"""

DICTATION_PHRASES = [
    {
        "id": 1,
        "level": "A2",
        "topic": "Daily Routine",
        "text": "What are you going to do this weekend?",
        "phonetic": "/wɒtəjə ˈɡənə duː ðɪs wiːkˈɛnd/",
        "feature": "Reduction ('going to' → 'gonna') & Weak form ('are you' → /əjə/)",
        "explanation_uz": "Jonli nutqda 'going to' qisqarib 'gonna' /ɡənə/ deb aytiladi, 'what are you' esa tez talaffuzda /wɒtəjə/ ga aylanadi."
    },
    {
        "id": 2,
        "level": "A2",
        "topic": "Social Greetings",
        "text": "It was nice to meet you yesterday.",
        "phonetic": "/ɪtwəz naɪstə ˈmiːtʃuː ˈjɛstədeɪ/",
        "feature": "Assimilation (/t/ + /j/ → /tʃ/) & Weak form ('to' → /tə/)",
        "explanation_uz": "'Meet' so'zidagi /t/ va 'you' so'zidagi /j/ birikib /tʃ/ (ch) tovushini hosil qiladi: /miːtʃuː/."
    },
    {
        "id": 3,
        "level": "A2",
        "topic": "Directions",
        "text": "You can turn right at the next corner.",
        "phonetic": "/jəkən tɜːn raɪt ətðə nɛks ˈkɔːnə/",
        "feature": "Elision (/t/ tushib qolishi 'next corner' → 'neks corner')",
        "explanation_uz": "Ikki undosh ketma-ket kelganda /t/ tovushi tushib qoladi: 'next corner' /neks kɔːnə/ deb eshitiladi."
    },
    {
        "id": 4,
        "level": "B1",
        "topic": "Past Advice & Regrets",
        "text": "I should have called you before leaving.",
        "phonetic": "/aɪ ˈʃʊdəv kɔːld jə bɪˈfɔː ˈliːvɪŋ/",
        "feature": "Weak form of 'have' (/həv/ → /əv/) & Contraction",
        "explanation_uz": "'Should have' nutqda 'should've' /ʃʊdəv/ deb talaffuz qilinadi. Ko'pchilik o'quvchilar 'should of' deb adashadilar."
    },
    {
        "id": 5,
        "level": "B1",
        "topic": "Requests & Politeness",
        "text": "Could you please pass me that bottle of water?",
        "phonetic": "/kʊdʒuː pliːz pɑːs mi ðæt ˈbɒtələv ˈwɔːtə/",
        "feature": "Assimilation (/d/ + /j/ → /dʒ/) & Linking consonant-to-vowel",
        "explanation_uz": "'Could you' birikib /kʊdʒuː/ (kuju) deb yangraydi, 'bottle of' esa /bɒtələv/ tarzida tutashib ketadi."
    },
    {
        "id": 6,
        "level": "B1",
        "topic": "Travel Plans",
        "text": "Hold on for a moment while I check the schedule.",
        "phonetic": "/həʊld ɒn fərə ˈməʊmənt waɪl aɪ tʃɛk ðə ˈskɛdʒuːl/",
        "feature": "Consonant-to-vowel linking ('for a' → /fərə/)",
        "explanation_uz": "Undosh bilan tugab unli bilan boshlangan so'zlar bitta so'zdek ulanadi: 'for a moment' /fərə məʊmənt/ bo'lib ketadi."
    },
    {
        "id": 7,
        "level": "B1",
        "topic": "Workplace Updates",
        "text": "We have been waiting for over an hour.",
        "phonetic": "/wiv bɪn ˈweɪtɪŋ fər ˈəʊvərən ˈaʊə/",
        "feature": "Weak forms ('been' → /bɪn/) & Linking /r/",
        "explanation_uz": "Britancha talaffuzda 'over an' o'rtasida linking /r/ tovushi paydo bo'ladi: /əʊvərən aʊə/."
    },
    {
        "id": 8,
        "level": "B2",
        "topic": "Environmental Science",
        "text": "Law and order is essential for sustainable development.",
        "phonetic": "/lɔː rənd ˈɔːdər ɪz ɪˈsɛnʃl fə səsˈteɪnəbl dɪˈvɛləpmənt/",
        "feature": "Intrusive /r/ (/lɔː/ va /ənd/ orasida)",
        "explanation_uz": "Yozuvda 'r' harfi bo'lmasa ham, unlilar orasida bog'lanish yengil bo'lishi uchun intrusive /r/ hosil bo'ladi: 'law /r/ and order'."
    },
    {
        "id": 9,
        "level": "B2",
        "topic": "Modern Technology",
        "text": "Go out and see if there is any network available.",
        "phonetic": "/ɡəʊ waʊt ənd siː ɪf ðɛər ɪz ˈɛni ˈnɛtwɜːk əˈveɪləbl/",
        "feature": "Intrusive /w/ linking ('Go' /əʊ/ + 'out' /aʊt/ → /ɡəʊ waʊt/)",
        "explanation_uz": "Dudoq unlisidan keyin unli kelsa, oraliqda /w/ tovushi paydo bo'ladi: 'go /w/ out'."
    },
    {
        "id": 10,
        "level": "B2",
        "topic": "Hypothetical Situations",
        "text": "You could have told me you were not coming.",
        "phonetic": "/jə kədəv təʊld miː jə wɜː nɒt ˈkʌmɪŋ/",
        "feature": "Multiple reductions ('could have' → /kədəv/, 'you were' → /jə wɜː/)",
        "explanation_uz": "Modal fe'llar va olmoshlar yordamchi bo'lgani sababli urg'usiz holatda reduksiyaga uchraydi."
    },
    {
        "id": 11,
        "level": "B2",
        "topic": "Academic Research",
        "text": "Most students would rather study online than in a lecture hall.",
        "phonetic": "/məʊst ˈstjuːdnts wəd ˈrɑːðə ˈstʌdi ˈɒnˌlaɪn ðən ɪnə ˈlɛktʃə hɔːl/",
        "feature": "Weak forms ('than in a' → /ðən ɪnə/) & Contraction",
        "explanation_uz": "'than in a' uchala qisqa so'z bitta ritmik guruhga birlashib ketadi."
    },
    {
        "id": 12,
        "level": "B2",
        "topic": "History & Heritage",
        "text": "They walked through the old town to reach the castle.",
        "phonetic": "/ðeɪ wɔːkt θruː ðiː əʊl taʊn tə riːtʃ ðə ˈkɑːsl/",
        "feature": "Elision of /d/ ('old town' → /əʊl taʊn/)",
        "explanation_uz": "'old' so'zidagi /d/ keyingi /t/ undoshi ta'sirida tushib qoladi (elision)."
    },
    {
        "id": 13,
        "level": "C1",
        "topic": "Economics & Policy",
        "text": "Had he known about the delays, he wouldn't have agreed to the proposal.",
        "phonetic": "/hæd iː nəʊn əˈbaʊt ðə dɪˈleɪz hiː ˈwʊdntəv əˈɡriːd tə ðə prəˈpəʊzl/",
        "feature": "Inversion, H-dropping ('Had he' → /hæd iː/) & Double reduction ('wouldn't have')",
        "explanation_uz": "Tez nutqda 'he' so'zidagi /h/ tushib qoladi (/hæd iː/), 'wouldn't have' esa /wʊdntəv/ ga qisqaradi."
    },
    {
        "id": 14,
        "level": "C1",
        "topic": "Philosophy & Psychology",
        "text": "It is not quite clear what they are trying to achieve.",
        "phonetic": "/ɪts nɒt kwaɪt klɪə wɒt ðeɪ ə ˈtraɪɪŋ tə əˈtʃiːv/",
        "feature": "Glottal reinforcement & weak prepositions",
        "explanation_uz": "'not quite' va 'what they' birikmalarida /t/ tovushlari ko'pincha glottal stop [ʔ] bilan almashtiriladi."
    },
    {
        "id": 15,
        "level": "C1",
        "topic": "Scientific Innovation",
        "text": "She would have been working there for a decade by next month.",
        "phonetic": "/ʃi wədəv bɪn ˈwɜːkɪŋ ðɛə fərə ˈdɛkeɪd baɪ nɛks mʌnθ/",
        "feature": "Triple auxiliary reduction: 'would have been' → /wədəv bɪn/",
        "explanation_uz": "Uchta yordamchi fe'l ('would have been') birgalikda atigi 3 ta qisqa bo'g'inga aylanadi: /wədəv bɪn/."
    },
    {
        "id": 16,
        "level": "C1",
        "topic": "Global Affairs",
        "text": "Far and wide, citizens gathered to protest against the fiscal policy.",
        "phonetic": "/fɑːr ən waɪd ˈsɪtɪznz ˈɡæðəd tə prəˈtɛst əˈɡɛnst ðə ˈfɪskl ˈpɒləsi/",
        "feature": "Linking /r/ ('far and' → /fɑːr ən/) & weak 'and' (/ən/)",
        "explanation_uz": "'Far and' birikmasida /r/ paydo bo'ladi va 'and' shunchaki /ən/ sifatida talaffuz qilinadi."
    }
]


def get_all_phrases():
    return DICTATION_PHRASES


def get_phrase_by_id(pid):
    for p in DICTATION_PHRASES:
        if p["id"] == pid:
            return p
    return None
