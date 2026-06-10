- **Prioritize the text/speech-to-audio-matching problem as the main AI use case.**  
  In the discussion, the experts treated the core AI task as taking a participant’s spoken or typed music preference, converting speech to text if needed, and matching that text against audio metadata or stems. They explicitly distinguished this from the movement-to-sound-control part, which they described as currently non-AI and already handled statistically.

- **Treat speech-to-text plus text-to-text matching as the simpler and more feasible near-term path.**  
  One expert said that converting speech to text or taking direct text input and then comparing it with audio metadata “should be simpler.” They also said that, if metadata is missing or inadequate, it is possible to extract more relevant metadata from the audio first and then perform text-to-text matching.

- **Use existing embedding/LLM methods for matching text requests to music metadata.**  
  The experts said this matching task should be relatively simple using LLMs or embedding models. They suggested a workflow where audio metadata is embedded in advance, the user query is converted into embeddings, a retriever brings back top matches, and an LLM ranks them to find the best result.

- **Metadata quality is central to retrieval performance.**  
  The discussion repeatedly emphasized that matching accuracy depends on how the music is described. One expert noted that the key question is what the actual metadata contains—whether it includes specific audio features, overall descriptions, tone, or other text. Later they stated that if the metadata is good, the agent should be able to find the top-matching audio.

- **Generate metadata for existing and future audio assets as a one-time or occasional pipeline step.**  
  The experts suggested that if audio metadata is not already available, models should be able to generate textual metadata from audio. They described this as a one-time task for the current audio set, with additional runs only when new audio becomes available. They said processing the current set could take “one day or so,” depending on whether it runs locally or via API.

- **Start with a small proof of concept before scaling the dataset.**  
  The recommendation in the meeting was to begin with a small number of audio metadata records just to test how the voice agent works, then increase the metadata and generate more if needed. The experts framed this as a proof-of-concept approach before investing in a larger database.

- **If the collection is small, embeddings may not be necessary initially.**  
  One expert said that with only a few hundred audio items, embeddings may not be needed because current LLM context windows are large enough; a simple LLM call could suggest the best matching audios. They suggested embeddings become more useful if the collection grows to several thousand items.

- **If scaling up, store embeddings and use similarity search.**  
  For larger collections, the experts recommended generating embeddings with OpenAI embedding models such as text-embedding-3-large, -medium, or -small, storing them in something like a Postgres database, and then using cosine similarity to match new text queries against the stored audio metadata.

- **Consider an agent-based approach instead of manually orchestrating the logic.**  
  Janne suggested using an OpenAI voice agent / agent SDK so that the agent can decide how to search the database based on the user request. The example given was that if a user asks for “80s music with 120 or 130 BPM,” the agent could decide to combine metadata filtering with embeddings. Another expert agreed this was “even better” and said a voice agent is a good idea because it can automate the tasks previously described.

- **Use GPT-4o Transcribe for English speech recognition.**  
  When asked what to use for speech recognition, the recommendation was GPT-4o transcribe. It was described as working very well for English and accessible through OpenAI’s API. The experts also noted that local use of comparable open-source models would require GPU resources, making API use a practical option.

- **OpenAI APIs/frameworks were presented as a low-effort implementation route.**  
  The experts said speech-to-text can be accessed through OpenAI’s API with only a couple of lines of code, and they described the broader OpenAI framework and agentic tools as requiring relatively little code compared with building the system manually. They also mentioned sharing links to newer OpenAI models for this purpose.

- **Build the database and metadata schema carefully; this was described as the more central task.**  
  Although the framework work was described as lightweight, Janne noted that the bigger practical issue is “how to build a database and go into metadata in a specific format.” Another participant added that building the dataset of audio descriptions is a central AI task in this project.

- **Use user testing to validate whether matching quality is acceptable.**  
  The client said the ultimate goal is to test with people and see whether they are annoyed because results differ too much from what they asked for, or whether the returned music matches expectations such as “120 BPM.” This was accepted in the conversation as the real evaluation of whether the system works.

- **Do not prioritize AI for the current movement-to-sound pipeline unless there is a strong reason.**  
  The client explained that movement is currently mapped to sound via statistical methods using measures like acceleration, velocity, location, filtering, and spatialization. The experts questioned why this should be replaced with generative AI if it already works, and one expert said they expected AI would increase latency and might not be as responsive as the current statistical method.

- **Treat movement-to-sound AI as exploratory rather than practical for now.**  
  The client expressed curiosity about a transmodal model that could relate human movement to sound processing in real time, but also acknowledged it as a much harder task. The experts responded that they were not sure such a model exists in a form suitable for this use case, and that even if it did, it would likely add latency.

- **Avoid adding textual reinterpretation stages for sensor data if responsiveness matters.**  
  One expert proposed, only as an alternative, converting sensor data into textual representation and sending it to an LLM for interpretation, but immediately noted that this would increase the pipeline and therefore responsiveness concerns.

- **For audio generation and library creation, the client identified dataset creation and diversity as unresolved practical questions.**  
  The client said they may want to generate hundreds or thousands of minute-long compositions and then extract metadata from them, but that the size and diversity of this material remain open questions. They also mentioned potentially using tools like Suno or Udio to generate diverse songs, and said manually curating these by hand would be a poor approach.

- **The experts framed metadata generation for a growing music library as parallelizable and operationally manageable.**  
  In response to the client’s concern about building a large set of generated music plus metadata, the experts noted that metadata generation only needs to be rerun when new audio is added, rather than continuously, which positions it as a manageable operational step rather than a recurring daily burden.

- **Keep the current system architecture in mind: offline preference input plus real-time movement input.**  
  The client described the system as having an offline input stage where the participant states the kind of music they want, and a real-time input stage where movement affects the sound. Recommendations in the meeting focused AI efforts on the first stage rather than the second.

- **Follow-up support was explicitly offered after experimentation.**  
  The experts said the client could run experiments, especially around the metadata/agent proof of concept, and then return to them for another look and further direction. They also said they would summarize the meeting in a report and include links and specific suggestions to try.