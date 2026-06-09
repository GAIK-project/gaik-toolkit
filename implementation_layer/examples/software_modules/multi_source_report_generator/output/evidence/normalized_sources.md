## Source 1: framerate.mp3
Type: audio
Path: C:\Users\h02317\gaik-toolkit\implementation_layer\examples\software_modules\multi_source_report_generator\sample_inputs\framerate.mp3


[Timestamp: 00:00 - 21:01]
Okay, so
hello and I think you were not present in the last meeting so I recall connectedly so
I hope you have seen our report
so the purpose of this meeting was to discuss
more technical details like how you are currently doing this what models you are using and what
current problems are so we did get some high-level details from your colleague but
he said that you work on more technical level so you'll know more details so could you please
describe the current status of development or what current challenges you have? Yeah, absolutely. I
mean the system that we're working with is
in the same team that previous spoke is pretty complicated on that note and it's utilizing a
called Maximus P which I've utilized for many years which is a program for really combining
a bunch of different types of media and different sensors and things like that and Maximus P is the
software hub and then I'm getting serial data from ultrasonic sensors, the hardware and these
are very cheap. They're very inexpensive sensors and we've also determined that while they kind
of get this project off the ground they're not the best option and the sensors are coming in
to this program app which I'm then mapping to sound. I'm mapping to lighting so all of those
processes are statistical methods or just by hand methods so in that context and in the current
status the system there's actually no machine learning. There's no works in that context
but to kind of give you a broader overview of what we'd like to do which is if you do understand
that I can give you some more technical details and you kind of expressed the premise that we're
working with so we now have the statistical model and by hand system for converting movement from
sensors to sound and lighting which is very exciting, very cool. So it's not a generative AI model?
It's not a generative AI model, correct. Yes, it's not. The current state is it's not but what we're hoping
is to move towards that and in particular having this free process for people experiencing this
or participants of speaking or equivalent, you know, typing because speech to text is very material
what kind of music they're interested in. So let's say you wanted, you know, I don't know,
saxophone jazz. You could say saxophone jazz. That would go into a speech recognition model
that would give us, you know, the token saxophone jazz. Then my thought and this is more hand-wavy
is to do some kind of fuzzy merging on that text to a bunch of generated, already generated musics.
The air generating music on the fly is very low. It's much faster than it has been but the idea of
creating a stream of saxophone jazz, you know, within milliseconds or even seconds of a participant
saying that is a difficult problem right now. So yes, if I could simplify it speech to text
that gets a particular interesting music that they want that's been mapped to a big database
of different types of music and each of those musics is then loaded into Max or some other
software that can play that sound and process sounds and then their movement from the sensors
that affects the sounds and ideally the sound would be manipulated on a stem basis. So if you
have a band that would be, you know, rock, bass, drums, bass, guitar, saxophone, each of those would
be isolated so the stems would be there and then, you know, if you move your head maybe that's going
to affect the drums. You move, I don't know, your hips that could be the saxophone something like
that. So being able to have individual control of the musical elements I think would be really
interesting. The AR part is to do this matching of user's speech and find one or more matching
audios. So what matching code, is it just speech or text or is there something else too?
In the context of the system there's an offline input which would be the pre-message of like I
want this type of music and then a real-time input which would be the movement and that could
be a statistical method that's what I've been doing but that would also maybe be interesting
to play around with in the context of generating AR but the main question in AR I guess that would
be useful to discuss would be yeah going from text into painting from a database or a set of
Yeah, so I think if we do this text-to-text matching that should be simpler.
So we convert speech to text or we directly get text input and then we compare it with
audio metadata and it is also possible to extract more relevant metadata from audios.
If you do not have adequate data available and then you just do a text-to-text matching and
there are many ways to do that using this LLM for embedding models it should be a simple task.
What do you think? Yeah, I think it starts with a complicated case like a person gives text or
description and then it depends like how do we describe the music or like what is the metadata
do we give like some specific audio features and overall description or what is the actual
metadata but the current audio processing models are very efficient especially speech-to-text
models are very efficient. I'm not sure if I don't remember any model that can
generate metadata for audios but there must be models. Yeah, I'm pretty sure that there must be
even some open source models available. So I think you can generate metadata.
How many audios are there? A few hundreds or thousands?
It's a process where we haven't generated that so that's another question. I mean I have ideas of
how to generate a bunch of musical material and then as you're saying extract that metadata from
it but yeah the question is size and like diversity of that data. So normally how long
the audio file is or what is the duration, average duration? Yeah, I mean in the past we've had the
system play for a minute before having people kind of move on from it so it would be a case
of generating I don't know hundreds of thousands minute long little compositions. Yeah, so I think
it's a one-time task. You do not need to do this every day. So every time you have some new audios
available you can generate metadata and for the current audios you can run this model one time.
It may take one day or so and it can generate the whole data. Now the question is whether it runs
locally or via some API but I'm pretty sure that there are such models available that can
that can extract metadata from audios like they can describe audios something like that.
Yeah. And yeah, so I think it should be a simple task.
So regarding the other states in the pipeline like where you find the metadata and then you
manipulate it through hand movements or maybe body movements that is something that
I don't think is AI related. So I'm not sure like how do you do this? How do you currently do this
or how do you plan to do this? Yeah, yeah, yeah. I can do that. Like I said through like by hand
statistical methods of let's say you had you're getting information about movements you can get
statistics on that like acceleration, velocity, location and each of those can be mapped to
musical brightness through that filtering. It could be related to position because we have a
speaker array so not just one speaker. So the location of the person can correspond to
but I do think it's possible to do this through generative AI not in the sense of generating music
but a like a transmodal model that allows you to go from movement onto sound processing.
I know that that's a very much harder task especially to be able to do real time
than just like text. As I understand you are doing this statistical analysis and
sending data to some mixer or something which will change the value. But if you are successfully
doing it by this statistical method why do you want to do this through generative AI?
I'm not, I mean it's a good question. I think personally it's effective now but I think there's
a curiosity in me especially of like movement and music have such an intimate relationship
and so some kind of model that matches a human movement to sound processing or any kind of like
manipulation of sound would be intriguing to me. I mean you bring up a good question in the sense of
like it's working now. It's a system that functions and is interesting I think but I just have a
curiosity of if there is a way to build some kind of model that would relate those two things in
real time and be efficient doing that. Yeah but I think it will just increase latency because
I'm not sure whether there is any such model which can calculate movements to
audio signals or something. Even if it is a generative AI model so I think it will not be
as responsive as your statistical method is. And another way to do this is to convert this sensor
data into textual representation and then send it to an LLM and then let it interpret it and but then
again will increase the pipeline and it will introduce latency. So you need a very efficient
lightweight AI model that can convert this movement data to sound data and if there is such a model
existing it may not be a lightweight model as I understand. Yeah yeah I think I mentioned that
especially with audio processing and generation it's a pretty big guy and that's why I've avoided
that entirely with the system. Yeah I'm not aware of any such model
even if such a model exists and has to pass and use it runs locally of course then there will be
problems with computing hardware and yeah I don't expect low latency. Yeah yeah and that's essential
to the system because I think as soon as it breaks down into any kind of you know effect around
trip between movement and sound generation especially with these you know kind of for
people but even to 100 milliseconds feels kind of kind of gummy. Yeah and then you will lose
synchronization between


[Timestamp: 21:01 - 42:02]
agent with these you know kind of for
people but even to 100 milliseconds feels kind of kind of gummy. Yeah and then you will lose
synchronization between
in the vicinity close vicinity
and your the user theory
is converted into embeddings
and the retriever
brings the top five matches
and an LLM does the ranking
to find the best match
something like this
so I think that's the most reasonable
way to do this
I guess for me
if I were to do something
in the context of like a Python
or even in the fact that it's
distributed or anything like that
what would be suggestions
for speech recognition
or suggestions for these text embeddings
what's the language
more common language like
is it Finnish
the language everything should be English
so you can use
these GPT-4O
transcribe models
it works very well for English
it's very good
so it's an advanced version
of this whisper model
from OpenAI
and whisper is also an
open source model
but for running it locally
you will need some GPUs
so you can use it via
OpenAI API
so GPT-4O transcribe
is very good
for many languages
including English
of course it has that
performance for English
so that's what we use
for speech to text conversion
and then
you can try this
embedding methods
like you already have
these embeddings stored
and every time
you have a request
you create the embedding
and do this comparison
what do you think about it
I'm just asking about
what would be the answer point to that
so for example
I would have
just for technical purposes
a text document which includes
a bunch of examples
requests of the input
and then I would have
training data which would be
metadata extracted from
I don't know a thousand audio files
for me I don't have experience
of what the next step would be
for statement O2
to find these embeddings
I guess that's what I'm interested in
and looking for
so simple to use
is speech to text models
you can access those models
through OpenAI APIs
it's just a couple of lines
of code, you input the audio
and it gives you
the text
and if it is
just a few hundred audios
you don't even need to create embeddings
because currently
the LLM context window size
is 2 gigs
but maybe if you have
several thousand audios
then it's good to convert them into embeddings
and again
you can use these embedding models
from OpenAI
for instance
this
text 3 large
model something like this
or text 3 medium
or text 3 small
so they can generate embeddings
there are various models
they can generate these embeddings
you can store them
in maybe
in some Postgres database
and then
every time you have this text
you can
convert it into embedding
using the same model
and then you can do this
cosine similarity
matching
so again there are
methods or functions
available to do that
and if you have
some like a few hundred
metadata
of audios you don't even need
these embeddings
you can just do a simple
LLM call and it can
suggest the best
matching audios
I'm not sure
how long it can work
maybe
for thousand two thousand audios
what do you think?
metadata could be very small
well it depends
I would say
maybe like
for example
OpenAI
framework
I think
basically
this line
or maybe twenty lines
to get a rank
it's a business
straightforward
if it comes to
building this database
and collecting the data
it's a specific format
then
yeah
I think
the building of the database
is a generative AI task
in the sense that
if I was going to be
going to Juno
or Udio or one of these tools
that generates audio
and saying
give me you know
a hundred diverse songs
which is such an impossible task
but I think that that would be
another element
that I'd be curious about
parallelizing. Of course I could do this
you know by hand
and just run it through and pick things
but that's a terrible idea
there's an actual
for API so you can
build up your songs
or build up your pieces
yeah I have
interesting things to look into
I have sent a
link in the chat
so these are OpenAI's
new speech models
and they can be used
in an agentic approach
that Yan made us mention
so it would be good
to test them
I think using a
voice agent is a good idea because it will
do everything automatically
it will do all these tasks that I just
mentioned so you don't need to
worry about it and usually
you just use a simple
chat response
or some other API
a few lines of code
not more than this
ok and
yeah maybe you need to
build this dataset
audio transcript
but maybe you can start
with a few
audio metadata
just to test how this voice agent
works just as a
proof of concept
and then you can increase the metadata
you can generate more metadata
yep
if that's needed
the ultimate goal is
testing with people and seeing if they
are pissed off
that it's too different from what they asked for
or it's right on
and they get the 80 drops
as 120 BPM
like they want
yeah so it all depends
on the
metadata like if you have good
metadata of course the agent will be able
to find
this is the top matching
audio
yeah
yeah
so
you can do this experiment
and then you can come back to us
maybe we can take a look at your
progress again
and
do some more brainstorming
I really appreciate
sorry to skip out there
I mean
yeah
my dear
ok I was just wondering
still a bit unclear
just how much
help are we
hoping
to get from you
so
we have different services
like you can apply for
more AI advisory services
like this AI advisory meeting
and we can review
your current progress
we can do more brainstorming
provide you more suggestions
and
another service
is the scope of concept
prototype
where we build
some proof of concept
for the company but
this is a rather simpler task
so we don't think
it needs
a proof of concept service
so a better way to do this
is that you
try this on your own
we can do another meeting
and see what you have done
and maybe
give you more suggestions
so I think this
will be a good way to proceed
with this
what do you think Eino?
yes
it's exactly that
basically
you need to be able
to develop your solution
pretty much the way
as we were
discussing here
the way of pointing
that it is
let's say
commercially ready
to be
accelerated
like in a better way
and then we have
this kind of
test based services
and also
some financial
services that help
you in
getting more investment
but
for
now
I would say
that
you first
develop
the solution
that you have
already
quite far
developed at least
in terms of the training
and
then we have
a follow up
meeting
I guess
now in a month
or two
that we will take
this and
then we see
after that where you are
and what possibilities
then further
this will have
within the
fair
but probably
you got
a question
about
how we can help
you in
developing
your own system
what we can
provide is
advisory
and comments
and use
KPIs
but
development
needs to
happen
by yourself
I understand
yeah
like I said
that we have
different services based on
the complexity of the use case
in some cases
we also
offer
masters thesis service
where we recruit
a student to do some research
and build some solution
and in some cases
we build proof of concepts
but
I don't think this
use case requires
building a proof of concept
because it's a rather simpler
use case, we can help you
like in the form of
more AI advisory
meetings and I'm pretty
sure that you will be able to do
this by the next meeting
because it's a rather simpler task
so as for the
next meeting are we then
are we looking then
early
for the next meeting
or something like that
or can we do
something in late before
if that's possible
or feasible
anyway in July we cannot do
anything that's clear
late June is possible
I don't know
my perspective is
that cadence is fine
yeah it sounds good
time around
in the whole June
so let's
maybe the week after
the summer is okay for you
well
you are not around
in June
yeah
I'm available by mid of June
the 15th of June
not after that
so
yeah
I mean
I think that the
before the 15th
would be reasonable for
so I can
send you a booking
link, you can see the available
slots
and
you can only find slots
before 9th of June
sure
and
yeah
okay so this is the link
and
yeah
and then we will also
