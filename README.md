# underwood-gpt-agenda
Mr. Underwood is a generative personal assistant living inside an Underwood 3500 electric typewriter. He prints a daily agenda by pulling high-priority items from your Gmail inbox and Google Calendar, and adding in some local events, weather and alerts.

The Underwood 3500's logic board is wired to an Arduino Nano Every, which simulates keypresses (to type on the typewriter) and monitors real keypresses (to receive incoming data). The Nano is connected via USB serial to a Raspberry Pi Zero 2 W, which configures preferences and wifi, calls a handful of APIs and generates a daily agenda printed to the typewriter, via this script.

Services and APIs used:
- Google (Gmail, Calendar, People, Geolocation & Geocoding APIs)
- OpenAI (gpt-4-turbo API)
- Bing (News Search API)
- NWS (Weather API)

Mr. Underwood builds on the work of multiple technologists who pioneered interfacing with functionally identical (other than a re-brand) Olivetti Praxis 35 typewriters in the 1980s:

- "An Inexpensive Letter-Quality Printer," Stuart Brown, BYTE, May 1983
- "Typewriter to daisywheel printer," Neil Duffy, Wireless World, August 1983
- "Cheap Daisy Blossoms," Gary Kaufman, Micro Cornucopia, October 1983
- "A Centronics-type microcomputer parallel interface to Olivetti Praxis typewriters", R. S. Tse, Journal of Microcomputer Applications (1987)

Additional gratitude is due to 1ST1, forum member @ vcfed.org and classic-computing.de, whose detailed documentation of Olivetti Praxis typewriters going back many years made this project possible.

Contact:
- Josh Sucher
- josh@thingswemake.com
- https://github.com/joshsucher

"Age could not cloud his vision or close his mind / he died as he had lived / eyes open to the future / eternally young." - John Thomas Underwood's epitaph. Green-Wood Cemetery, Brooklyn, 40.653821, -74.000014