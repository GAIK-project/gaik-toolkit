- **Current phase: existing non-AI system, with AI still at ideation / early proof-of-concept stage**
  - The client said their current system is “an extension of what Max previously spoke” and is built around **MaxMSP** as the software hub.
  - The current setup takes **serial data from inexpensive ultrasonic sensors** and maps that movement data to **sound and lighting**.
  - They stated explicitly that the current system uses **“statistical methods or just by hand methods”** and that **“the current status of the system is actually no machine learning.”**
  - They also confirmed it is **not a generative AI model** at present: “The current status is not.”

- **What already exists today**
  - They already have a working pipeline where **movement from sensors is converted to sound and lighting**.
  - They described the existing movement-to-audio control as functioning through **statistical analysis of sensor data**, including measures such as **acceleration, velocity, and location**.
  - These movement features are then mapped to audio properties such as **musical brightness/filtering** and **spatialization/virtualization** in a speaker array.
  - The client said the system is already **“working now”**, and also described it as **“a system that functions and is interesting.”**

- **Known limitations of the current setup**
  - The current hardware relies on **very cheap ultrasonic sensors**, which they said helped “get this project off the ground,” but they also stated that these sensors are **“not the best option.”**
  - They have **not yet generated the music dataset** they are considering using. They said, “This is a process where we haven’t generated stuff.”
  - They are still uncertain about the **size and diversity of the audio data** they would need.

- **What they want to build next with AI**
  - Their stated direction is to **move toward AI**, especially around an interaction where a participant can **speak or type what kind of music they want**.
  - The intended flow is:
    - **speech-to-text** or direct text input,
    - extract the requested music description (example given: “saxophone jazz”),
    - **match that text to music** from a database of generated or pre-generated tracks,
    - load the selected music into Max or similar software,
    - then continue using movement input to manipulate the playback.
  - They described the **main AI question** as going **“from text into finding from a database or stems”** and later clarified that the AI part is to **match user speech/text to one or more appropriate audio files**.

- **What is not currently planned as the primary AI component**
  - They distinguished the **audio-selection step** from the **movement-control step**.
  - They said that for **initially picking matching audio from the database**, it is **just about text or speech**, and **hand/body movement is not part of that matching step**.
  - The movement-based manipulation of sound is currently handled by non-AI statistical methods.

- **Aspirational / exploratory AI ideas beyond the main matching task**
  - The client expressed curiosity about a more advanced model that could relate **human movement directly to sound processing in real time**.
  - They described this as an **intriguing possibility**, but also acknowledged it as a **much harder task**, especially in real time.
  - They also acknowledged that the current statistical method is already effective, saying: **“it’s effective now”** and questioning whether AI is necessary there.

- **Current readiness for AI implementation**
  - They already have:
    - a **working interactive system**,
    - an existing **software environment (MaxMSP)**,
    - a clear understanding of the current non-AI pipeline,
    - a defined potential AI use case around **speech/text-to-audio matching**.
  - What still needs development:
    - a **music database / dataset** of generated or collected audio,
    - **metadata** or descriptions for those audio files,
    - the actual **speech-to-text + text matching pipeline**,
    - possible handling of **stems** if they want fine-grained control over separate instruments.

- **What they are currently looking for**
  - The client said they are interested in the **next step** for implementing the text-matching system, especially:
    - how to go from example user requests,
    - to audio metadata from many files,
    - to defining and using **embeddings**.
  - They specifically said: **“I guess that’s what I’m interested in and looking for.”**
  - They also asked what would be **suggestable for speech recognition** and what would be suggestable for **text embeddings**.

- **Immediate practical objective they discussed**
  - They said it may make sense to start with **a few audio metadata items just to test how the voice agent works**, explicitly in the context of a **proof of concept**.
  - Their **ultimate goal** was described as **testing with people** and seeing whether the retrieved music matches what participants asked for closely enough.

- **Aims and objectives for AI implementation**
  - Enable participants to **request music by natural language** (speech or text).
  - Use AI to **find the best matching audio** from a database, rather than generate music on the fly.
  - Potentially support **stem-based playback**, where different body movements affect different musical elements such as drums, bass, guitar, or saxophone.
  - Longer-term, explore whether there is any viable way to build a model that **relates movement to sound processing in real time**, though this was framed as exploratory curiosity rather than the main immediate deliverable.