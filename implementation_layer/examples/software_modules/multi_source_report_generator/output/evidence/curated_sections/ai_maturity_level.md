- **Current business operations / system purpose**
  - The company is working on a system for interactive movement-based sound and lighting. The current setup uses **MaxMSP** as the software hub, with **serial data from ultrasonic sensors** feeding into the system.
  - Sensor inputs are mapped to **sound** and **lighting**. The participant’s movement affects audio parameters, and the team has also discussed a workflow where a participant could specify desired music by **speaking or typing** a description.

- **Current services / functionality offered**
  - The current system converts movement from sensors into sound and lighting effects using **statistical methods** and **manual mappings**.
  - In the current implementation, movement data such as **acceleration, velocity, and location** can be mapped to audio properties such as **musical brightness/filtering** and **spatialization** across a **speaker array**.
  - In past use, the system has played for about **one minute** before participants moved on from it.

- **Current AI maturity status explicitly stated in the meeting**
  - The participant stated: **“the current status of the system is actually no machine learning.”**
  - They also explicitly confirmed: **“It’s not a generative AI model, correct. The current status is not.”**
  - The current system is described as **“a statistical model and by hand system for converting movement from sensors to sound and lighting.”**

- **Development stage**
  - The current system is already functional: the participant said **“it’s working now”** and described it as **“a system that functions and is interesting.”**
  - AI-related capabilities are still at the **idea / exploration / proof-of-concept** stage. The discussion focused on what they **would like to do**, such as:
    - speech-to-text for participant input,
    - matching text descriptions to music in a database,
    - potentially generating or curating a larger music library,
    - testing with a small metadata set first as a **proof of concept**.

- **Data availability**
  - The team does **not yet have an established audio dataset/library** for the proposed AI workflow. The participant said: **“This is a process where we haven’t generated stuff, so that’s another question.”**
  - They discussed the need to generate **hundreds or thousands of minute-long compositions** and then extract metadata from them.
  - The discussion identified **metadata quality** as important for matching user requests to audio, and noted that metadata may need to be generated if it is not already available.

- **Technical expertise**
  - The participant has used **MaxMSP for many years** and has experience building the current sensor-driven multimedia system.
  - They stated they have experience with **audio-to-audio language models**, but **not** with **text-to-audio** workflows.
  - The participant asked for guidance on practical implementation details such as **speech recognition**, **text embeddings**, and the **entry point** for building a retrieval pipeline, indicating they are still seeking support on the AI implementation side.

- **Workflow integration**
  - AI is **not currently integrated** into the live workflow. The present workflow relies on sensor data, manual/statistical mapping, and playback/manipulation of sound.
  - The proposed future workflow would separate:
    - an **offline input** step where the participant specifies the type of music they want by speech or text,
    - a **real-time input** step where movement manipulates the sound.
  - The participant explicitly noted that the movement-to-sound manipulation is currently being done without AI and questioned whether that part even needs AI.

- **AI roadmap / intended next steps discussed**
  - The primary AI use case under consideration is **speech/text-to-audio matching**, not on-the-fly music generation.
  - The intended approach discussed in the meeting was:
    - use **speech-to-text** or direct text input,
    - compare the text with **audio metadata**,
    - retrieve matching audio/stems from a database.
  - They discussed starting with a **small set of audio metadata** to test a **voice agent** or retrieval workflow, then expanding later.
  - The participant described the **ultimate goal** as testing with people to see whether the returned music matches what users asked for.

- **AI maturity classification**
  - **Low\*\***  
    - Relevant factual basis from the meeting:
      - the current system has **“actually no machine learning”**;
      - it is **not a generative AI model**;
      - current operations rely on **statistical methods** and **manual mappings**;
      - AI use cases are still being discussed as future possibilities / proof-of-concept;
      - required data assets for AI (generated audio library and metadata) are **not yet in place**;
      - the participant is still asking for guidance on core AI building blocks such as embeddings and speech recognition setup.