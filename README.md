# movie genre predictor
A neuron ai model that predicts genres based on video and audio features of a movie.

The current accuracy of the ai is 60%.

# how to use it?
Create a python virtual environment the recomended version of python is 3.11.

Inside the virtual environment run the folowing command from the project root.
```
python app/main.py
```

This will load the ai model and start the GUI.

# implementation
The ai model was trained through the jupyter notebooks that are in the `notebook/` subdirectory.
There is all the code along with explanations of it.

# data
The data used for machine learning were movies from personal sources.
Genres and other metadata were gethered through a `csfd-api` library in javascript.
The scraper code is in the `scraper/` subdirectory.
