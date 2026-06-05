import os
import re
import stanza
import spacy

nlp = spacy.load("en_core_web_sm")


def clean_text_transcription(text):
    text = text.lower()
    text = re.sub(r"[^a-zåäö0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


def clean_text_translation(text):
    return " ".join([t.lemma_ for t in nlp(text) if t.is_alpha])


def extract_technical_terms_nlpTool(input_file_path, output_folder, batch_size=200):
    nlp = stanza.Pipeline("fi")

    with open(input_file_path, "r", encoding="utf-8") as f:
        full_text = f.read()

    # sentences
    sentences = [s.strip() for s in full_text.split(".") if s.strip()]

    terms_set = set()
    keep_upos = {"NOUN", "ADJ"}

    # batch process
    for i in range(0, len(sentences), batch_size):
        batch_text = ". ".join(sentences[i : i + batch_size]) + "."
        doc = nlp(batch_text)
        for sentence in doc.sentences:
            words = sentence.words
            for j, word in enumerate(words):
                if word.upos == "NOUN":
                    terms_set.add(word.lemma.replace("#", ""))
                    # adjective checking
                    if j > 0 and words[j - 1].upos == "ADJ":
                        adj_noun = f"{words[j - 1].lemma} {word.lemma}".replace("#", "")
                        terms_set.add(adj_noun)

    # output
    os.makedirs(output_folder, exist_ok=True)
    output_file = os.path.join(
        output_folder, f"{os.path.splitext(os.path.basename(input_file_path))[0]}.txt"
    )

    # sorted unique terms
    with open(output_file, "w", encoding="utf-8") as f:
        for term in sorted(terms_set):
            f.write(term + "\n")

    print(f"Extracted {len(terms_set)} technical terms to {output_file}")
