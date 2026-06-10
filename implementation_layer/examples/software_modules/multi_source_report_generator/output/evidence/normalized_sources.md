## Source 1: framerate_transcript.txt
Type: text
Path: C:\Users\h02317\gaik-toolkit\implementation_layer\examples\software_modules\multi_source_report_generator\sample_inputs\framerate_transcript.txt


[Timestamp: 00:00 - 21:01]
Okay, so hello and I think you were not present in the last meeting so I will call connect people. I hope you have seen our report. So the purpose of this meeting was to discuss in more technical details like how you are currently doing this, what models you are using and what the current problems are. So we did get some high level details from your colleague but he said that you work on more technical level so you know more details. So could you please describe the current status of the movement and what current challenges you have? Yeah, absolutely. I mean the system that we are working with is kind of an extension of what Max previously spoke pretty confidently about and it's utilizing a program called MaxMSP which I have utilized for many years which is a program for really combining a bunch of different types of media and different sensors and things like that. And MaxMSP is the software hub and then I'm getting serial data from ultrasonic sensors, the hardware, and these are very cheap, they're very inexpensive sensors and we also determined that while they kind of got this project off the ground, they're not the best option. And the sensors are coming in to this program which I'm then mapping to sound, I'm mapping to lighting. So all of those processes are statistical methods or just by hand methods. So in that context and the current status of the system is actually no machine learning. There's no works in that context. But to kind of give you a broader overview of what we'd like to do, which if you do understand that can get into more technical details, and you kind of expressed this, the premise that we're working with, so we now have the statistical model and by hand system for converting movement from sensors to sound and lighting, which is very exciting and very cool.So it's not a generative AI model?It's not a generative AI model, correct. The current status is not. What we're hoping is to move towards that and in particular having this free process for people experiencing this or participants of speaking or equivalent, you know, typing because speech-to-text is very material, what kind of music they're interested in.So let's say you wanted, you know, I don't know, saxophone jazz, you could say saxophone jazz, that would go into a speech recognition model, that would give us, you know, the token saxophone jazz. And my thought, and this is more hand-weighty, is to do some kind of fuzzy matching on that text to a bunch of generated, already generated musics. The idea of generating music on the fly is very low, it's much faster than it has been, but the idea of creating a stream of saxophone jazz within milliseconds or even seconds of a participant saying that is a difficult problem right now.So yeah, to simplify it, speech-to-text, it gets a particular interesting music that they want that's been mapped to a big database of different types of music, and each of those musics is then loaded into Max or some other software that can play back sound and process sounds, and then the movement from the sensors that affects the sound. And ideally, the sound would be manipulated on a stem basis, so if you have a band that would be, you know, rock, a drum, bass, guitar, saxophone, each of those would be isolated, so the stems would be there, and then, you know, if you move your head, maybe that's going to affect the drums, you move, I don't know, your hips, that could be the saxophone, something like that, so being able to have individual control of the musical elements, I think would be really interesting.But that might not be the AI part, I understand correctly.Yeah, sure.
The AI part is to do this matching of users' speech and find one or more matching audios. But what kind of, is it just speech or text or there is something else too? In the context of the system, there's an offline input, which would be the pre-message of like, I want this type of music, and then a real-time input, which would be the movement. And that could be a statistical method, that's what I've been doing, but that would also maybe be interesting to play around with in the context of the generative AI, but the main question of AI, I guess that would be useful to discuss, would be, yeah, going from text into painting from a database or stems.Okay, initially, when it comes to picking the matching audio from the database, it's just about text or speech. It has not there this hand movement come into action. Okay.
You got it, yeah.
But if you have some metadata available for these audios, so should it not be a simple task to do with an LLM?
It's something that I have experience with in the context of audio to audio language models, that's my experience, but not something that is text to audio.
So, I think if we do this text-to-text matching, that should be simpler.
So, we convert speech to text or we directly get text input and then we compare it with audio metadata.
And it is also possible to extract more relevant metadata from audios if you do not have adequate data available and then you just do text-to-text matching and there are many ways to do that.
Using this LLM for embedding models, it should be a simple task. What do you say, Janne?
Yeah, I think this sounds not so complicated, like a person gives text or description and then it depends on how do we describe the music or what is the metadata.
Do we give some specific audio features and overall description or what is the actual metadata?
But the current audio processing models are very efficient.
If I really speak-to-text models are very efficient.
And I'm not sure if I don't remember any model that can generate metadata for audios, but there must be models available.
So, they can generate textual metadata, like maybe tone or maybe some other text.
Yeah, I'm pretty sure that there must be some.
Even open-source models available.
So, I think you can generate metadata.
How many audios are there? A few hundreds or thousands?
This is a process where we haven't generated stuff, so that's another question.
I have ideas of how to generate a bunch of musical material and then, as you're saying, extract metadata from it.
But yeah, the question is size and diversity of that data.
So, Narumani, how long the audio file is or what is the duration, average duration?
Yeah, I mean, in the past, we've had the system play for a minute before having people move on from it.
So, it would be a case of generating, I don't know, hundreds, thousands, minute-long little compositions.
Yeah, so I think it's a one-time task.
You do not need to do this every day.
So, every time you have some new audios available, you can generate metadata.
And for the current audios, you can run this model one time.
It may take one day or so, and it can generate the whole data.
Now, the first time is whether it runs locally or via some API.
But I'm pretty sure that there are such models available that can extract metadata from audios.
Like, they can describe audios, something like that.
And yeah, so I think it should be a simple task. So, and regarding the other steps in the pipeline, like there, you find the metadata, and then you manipulate it through hand movements or maybe body movements.
That is something that I don't think is AI-related. So, I'm not sure, like, how do you do this now? How do you currently do this, or how do you plan to do this?
Yeah, yeah, I currently do this, like I said, through, like, by statistical methods of, let's say, you have, you're getting information about movement, you can get statistics on that, like acceleration, velocity, location, and each of those can be mapped to musical brightness, so that's filtering. It could be related to position, because we have a speaker array, so not just one speaker. So, the location of the person can correspond to virtualization. But I do think it's possible to do this through generative AI, not in the sense of generating music, but a, like, a transmodal model that allows you to go from movements on to sound processing. I know that that's a very much harder task, especially to be able to do it in real time, than... But, so, as I understand, you are doing this statistical analysis and sending data to some mixer or something, which sends you value. But if you are successfully doing it by this statistical method, why do you want to do this through generative AI? I'm not, I mean, it's a good question. I think, personally, it's effective now, but I think there's a curiosity in me, especially of, like, movement and music have such an intimate relationship, and so some kind of model that matches a human movement to sound processing or any kind of, like, manipulation of sound would be intriguing to me. I mean, you bring up a good question, though, because it's a sense of, like, it's working now. It's a system that functions and is interesting, I think. But I just have a curiosity of, is there either way to build some kind of model that would relate those two things in real time and be efficient doing that? One up. But, yeah, that's a good way to put it. Yeah, but I think it will just increase latency, because I'm not sure whether there is any such model which can translate movements to audio signals or something. Even if there is, and if it is a generative AI model, so I think it will not be as responsive as your statistical method is. And another way to do this is to convert this sensor data into textual representation and then send it to an LLM and then let it interpret it. But then, again, it will increase the pipeline


[Timestamp: 21:01 - 42:02]
in this infinity,
and your,
the user query,
is converted into embeddings,
and the retriever brings the top five matches,
and an LLM does the ranking,
to find the best match, something like this.
I think that's the most reasonable way to do this.
I guess for me, if I were to do something in the context of like a Python text,
or even, you know, a fact that it's contributing or anything like that,
what would be suggestible for speech recognition,
or suggestible for these text embeddings?
What's the language?
More common language, like is it Finnish?
Wait, the language A should be in English.
English.
So you can use these GPT-4O transcribe models.
It works very well for English.
It's very good.
Yeah.
So it's an advanced version of this GitHub model from OpenAI.
And GitHub is also an open source model.
But for running it locally, you will need some GPU and another,
so you can use it via OpenAI's API.
So GPT-4O transcribe is very good for many languages, including English.
Of course, it has that performance for English.
So that can be used for speech-to-text conversion.
Okay, thank you.
And then you can try this embedding making.
Like you already have these embeddings stored,
and every time you have a request, you create the embedding and do this comparison.
What do you think, Juan?
I'm just asking about what would be the entry point for that.
So, for example, I would have, just for test makers, a text document,
which includes a bunch of examples, requests that would be input.
And then I would have training data,
which would be metadata extracted from, I don't know, a thousand audio files.
For me, I don't have experience of what the next step would be
for the statement of to define these embeddings.
I guess that's what I'm interested in and looking for.
So it is simple to use these speech-to-text models.
You can access those models through OpenAI's API.
It's just a couple of lines of code.
You input the audio and it gives you the text.
And if it is just a few hundred audios, you don't even need to create embeddings,
because currently the LLM's context window size is too big.
But maybe if you have several thousand audios,
then it's good to convert them into embeddings.
And again, you can use these embedding models from OpenAI.
For instance, this text3large model, something like this,
or text3medium or text3small.
So they can generate embeddings.
They are very cheap models.
They can generate these embeddings.
You can store them in maybe in some Postgres database.
And then every time you have this text query,
you can convert it into embedding using the same model.
And then you can do this cosine similarity matching.
So again, there are methods or functions available to do that.
And if you have some like a few hundred metadata of audios,
you don't even need these embeddings.
You can just do this simple LLM call and it can suggest the best matching audios.
I'm not sure how long it can work.
Maybe for thousand, two thousand audios.
What do you think?
The metadata could be very small.
Well, it depends.
I would say maybe like doing like for example OpenAI's voice agent SDK.
You can use the agents directly without this conversion to base.
So then if you do like an agent that takes input,
agent can decide how to search the database.
For example, if you say I want 80s music with 121 or 30 BPM,
then like agent decides, okay, we have metadata of this.
So we need to do this, use embeddings and this simple filtering.
This was correct.
Yeah, that's even better.
Yeah, like everything OpenAI framework, I think,
essentially we should basically like this line or maybe 20 lines.
It's a big, big framework.
This line comes to how to build a database and go into metadata in a specific format.
Yeah, I think the building of the database is a centered AI task.
In the sense that if I was going to be going through Juno or Udio or one of these tools that generates audio
and saying give me a hundred diverse songs, which is such an impossible task,
but I think that that would be another element that I'd be curious about parallelizing.
Of course, I could do this by hand and just run it through and pick things, but that's a terrible idea.
Yeah, actually it's a little app of API,
so you don't need to solve something like you want to do.
Yeah, that would be an interesting thing to look into.
I have sent a link in the chat.
So these are OpenAI's new feed models,
and they can be used in an agentic approach that Janne just mentioned.
So it would be good to test them.
So yeah, I think using a voice agent is a good idea because it will do everything automatically.
It will do all these tasks that I just mentioned, so you don't need to worry about it.
And usually you just use a simple chat response or some other API,
comes a few lines of code.
Not more than this.
Okay, and then yeah, maybe you need to build this data set of audio descriptions,
but maybe you can start with a few audio metadata just to test how this voice agent works.
Just as a proof of concept.
And then you can increase the metadata.
You can generate more metadata.
If that's needed.
I mean, the ultimate goal is testing with people and seeing if they are pissed off that it's too different from what they asked for,
or it's right on and they get the Airdrops as 120 BPM like they wanted.
Yeah, so it all depends on the metadata.
Like if you have good metadata, of course the agent will be able to find which is the top matching audio.
Yeah.
So you can do this experiment and then you can come back to us.
Maybe we can take a look at your progress again and give some more direction.
I don't know if that's the case.
Yeah, sounds good.
Let's keep in touch.
Okay.
Have a nice weekend then.
Take care.
Bye.
Bye.
Mol?
Mol?
Mol, are you there?
Mol?
Mol?
Are you there?
Mol?
Mol?
Mol, are you there?
Are you there?
Okay.
Okay.
Okay.
Mol.
Mol?
Mol, where is the car?
Okay.
Okay.
Okay.
Okay.
Yeah, maybe we will also summarize this meeting in a report.
We will send the report to you.
Maybe we will also add these links and other specific suggestions that you can try.
I appreciate it. Thank you very much.
Yeah, good stuff.
Thank you.
Thank you for being in touch.
Yeah, have a nice weekend then.
Take care.
Bye.
Yeah, bye.
Bye.
Bye.
Bye.
Bye.
Bye.
Mol?
Mol?
Mol, are you there?
Mol?
Mol?
Mol, where is the car?
Okay.
Okay.
Mol?
Are you there?
Are you there?
Okay.
Okay.
Okay.
Mol?
Mol, where is the car?
Okay.
Okay.
Yeah, maybe we will also summarize this meeting in a report.
We will send the report to you.
Maybe we will also add these links and other specific suggestions that you can try.
I appreciate it. Thank you very much.
Yeah, good stuff.
Thank you.
Thank you for being in touch.
Yeah, have a nice weekend then.
Take care.
Bye.
Yeah, bye.
Mol?
Mol?
Mol, are you there?
Mol?
Mol?
Mol, where is the car?
Okay.
Okay.
Mol?
Are you there?
Are you there?
Okay.
Okay.
Okay.
Mol?
Mol, where is the car?
Okay.
Okay.
Yeah, maybe we will also summarize this meeting in a report.
We will send the report to you.
Maybe we will also add these links and other specific suggestions that you can try.
I appreciate it. Thank you very much.
Yeah, good stuff.
Thank you.
Thank you for being in touch.
Yeah, have a nice weekend then.
Take care.
Bye.
Yeah, bye.
Mol?
Mol?
Mol, are you there?
Mol?
Mol?
Mol, where is the car?
Okay.
Okay.
Mol?
Are you there?
Are you there?
Okay.
Okay.
Okay.
Mol?
Mol, where is the car?
Okay.
Okay.
Yeah, maybe we will also summarize this meeting in a report.
We will send the report to you.
Maybe we will also add these links and other specific suggestions that you can try.
I appreciate it. Thank you very much.
Yeah, good stuff.
Thank you.
Thank you for being in touch.
Yeah, have a nice weekend then.
Take care.
Bye.
Yeah, bye.
Mol?
Mol?
Mol, are you there?
Mol?
Mol?
Mol, where is the car?
Okay.
Okay.
Mol?
Are you there?
Are you there?
Okay.
Okay.
Okay.
Mol?
Mol, where is the car?
Okay.
Okay.
Yeah, maybe we will also summarize this meeting in a report.
We will send the report to you.
Maybe we will also add these links and other specific suggestions that you can try.
I appreciate it. Thank you very much.
Yeah, good stuff.
Thank you.
Thank you for being in touch.
Yeah, have a nice weekend then.
Take care.
Bye.
Yeah, bye.