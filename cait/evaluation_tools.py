# -----------------------------------------------------------
# IMPORTS
# -----------------------------------------------------------

import os
import h5py
import numpy as np
import math

import matplotlib as mpl
import matplotlib.pyplot as plt

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.manifold import TSNE

from .evaluation._color import console_colors, mpl_default_colors
from .evaluation._pgf_config import set_mpl_backend_pgf, set_mpl_backend_fontsize

# -----------------------------------------------------------
# CLASS
# -----------------------------------------------------------


class EvaluationTools:
    save_plot_dir = './'
    save_pgf = False

    event_nbrs = None  # numeration of all events

    data = None  # can contain part of mainpar or events
    features = None  # normalized 'data'

    events = None  # 'events/event' from hdf5 file
    mainpar = None  # 'events/mainpar' from hdf5 file
    mainpar_labels = None  # 'events/mainpar'.attrs from hdf5 file

    pl_channel = None
    files = None
    file_nbrs = None
    events_per_file = None

    label_nbrs = None
    labels = None
    labels_color_map = None

    test_size = 0.50
    is_train_valid = False
    is_train = None
    predictions = None
    perdiction_true_labels = None

    color_order = mpl_default_colors

    scaler = StandardScaler()

    # ################### PRIVATE ###################

    def __add_data(self, data):
        """
        Adds data to the property data.

        :param data: list of floats, added to the property data
        """
        if self.data is None:
            self.data = data
        else:
            self.data = np.vstack([self.data, data])

    def __add_events(self, events):
        """
        Adds events to the property events.

        :param data: list of ints, added to the property events
        """
        if self.events is None:
            self.events = events
        else:
            self.events = np.vstack([self.events, events])

    def __add_mainpar(self, mainpar, mainpar_labels):
        if self.mainpar is None:
            self.mainpar = mainpar
        else:
            self.mainpar = np.vstack([self.mainpar, mainpar])

        if self.mainpar_labels is None:
            self.mainpar_labels = dict([(k, v) for k, v in mainpar_labels])
        else:
            for k, v in mainpar_labels:
                if k not in self.mainpar_labels:
                    if v in self.mainpar_labels.values():
                        raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                                         "Every label for the mainparameters must have a unique value.\n" +
                                         "Currently containing labels: {}\n".format(self.mainpar_labels) +
                                         "Tried to add: {}".format(mainpar_labels))
                    self.mainpar_labels[k] = v

    def __add_files(self, file):
        if self.files is None:
            self.files = [file]
            self.events_per_file = [0]
        else:
            if file not in self.files:
                self.files.append(file)
                self.events_per_file.append(0)

    def __add_label_nbrs(self, label_nbrs):
        if self.label_nbrs is None:
            self.label_nbrs = label_nbrs
        else:
            self.label_nbrs = np.hstack([self.label_nbrs, label_nbrs])
        self.__add_labels_color_map()

    def __add_labels_color_map(self):
        self.labels_color_map = {}
        for i, ln in enumerate(np.unique(self.get_label_nbrs('all'))):
            self.labels_color_map[ln] = self.color_order[i]

    def __add_labels(self, labels):
        if self.labels is None:
            self.labels = dict([(val, name) for (name, val) in labels])
        else:
            for name, val in labels:
                if (name, val) not in self.labels.keys():
                    self.labels[val] = name
        # self.labels = dict(sorted(self.labels.keys(), key=operator.itemgetter(1)))

    def __add_event_nbrs(self, event_nbrs):
        if self.event_nbrs is None:
            self.event_nbrs = event_nbrs
        else:
            self.event_nbrs = np.hstack([self.event_nbrs, event_nbrs])

    def __add_file_nbrs(self, file_nbrs):
        if self.file_nbrs is None:
            self.file_nbrs = file_nbrs
        else:
            self.file_nbrs = np.hstack([self.file_nbrs, file_nbrs])

    def __check_train_set(self, verb=False):
        """
        Checks wether there exists a seperation in a training and test data.
        If not then it genereates one with the property test_size.
        """
        if not self.is_traintest_valid:
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "No valid test set available. " +
                      "A test set of size {} is generated.".format(self.test_size))
            self.split_test_train(self.test_size)

    # ################### OTHER ###################

    def add_events_from_file(self,
                             file,
                             channel,
                             which_data='mainpar',
                             all_labeled=False,
                             only_idx=None,
                             force_add=False,
                             verb=False):
        """
        Reads in a labels, data from a channel of a given hdf5 file and
        adds this data to the properties

        :param file: hd5 file, file from which the data should be read
        :param channel: int, the number of the channel (e.g. phonon channel)
        :param which_data: string, default 'mainpar',select which data should be used as data (e.g. mainparameters, timeseries)
        :param all_labeled: boolean, default False, flag is set, include exactly the events that are labeled
        :param only_idx: list of int, indices only include in the dataset then only use these
        :param force_add: boolean, default False, lets you add a file twice when set to True
        :param verb: boolean, default False, if True additional messages are printed
        """

        # --------------------------------------------
        # INPUT HANDLING
        # --------------------------------------------

        # check if the file input has type string
        if type(file) is not str:
            raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                             "The variabel must be of type string and not '{}'.".format(type(file)))

        # check if the file is accessable
        if not os.path.isfile(file):
            raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                             "The given hdf5 file '{}' does not exist.".format(file))

        # check if the data key is correct
        if which_data != 'mainpar' and which_data != 'timeseries':
            raise ValueError(console_colors.FAIL + "WARNING: " + console_colors.ENDC +
                             "Only 'mainpar' or 'timeseries' are valid options to read from file.")

        # check if we look at a correct channel
        if type(channel) is int:
            if channel == 0 or channel == 1:
                self.pl_channel = channel
            else:
                raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                                 "Parameter 'pl_channel = {}' has no valid value.\n" +
                                 "(Use '0' for the phonon and '1' for the light)".format(channel))
        else:
            raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                             "Parameter 'pl_channel' has to be of type int.")

        # if file already exists ask again
        if force_add == True and self.files != None and file in self.files:
            print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                  "Data from this file already exists. Continue? [y/N]")
            cont = input()
            if cont != 'y' and cont != 'Y':
                return

        # --------------------------------------------
        # THE ACTUAL HAPPENING
        # --------------------------------------------

        # here the files are added as data source
        self.__add_files(file)

        with h5py.File(file, 'r') as ds:

            # check if the hdf5 set has events
            if 'events' not in ds.keys():
                raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                                 "No group 'events' in the provided hdf5 file '{}'.".format(file))
            # if the all_labeled flag is set, include exactly the events that are labeled
            use_idx = []
            if all_labeled:
                if only_idx is None:
                    length_events = ds['events/event'].shape[1]
                    only_idx = [i for i in range(length_events)]
                    del length_events
                for i in only_idx:
                    if ds['events/labels'][channel, i] != 0:
                        use_idx.append(i)
                nbr_events_added = len(use_idx)
            # elif we got a list of idx to only include in the dataset then only use these
            elif only_idx is not None:
                nbr_events_added = len(only_idx)
                use_idx = only_idx
            else:
                nbr_events_added = ds['events/event'].shape[1]
                use_idx = [i for i in range(nbr_events_added)]

            # find the index of the current file in the list of files
            file_index = self.files.index(file)

            if which_data == 'mainpar':
                self.__add_data(
                    np.delete(ds['events/mainpar'][channel, use_idx, :], ds['events/mainpar'].attrs['offset'], axis=1))
            elif which_data == 'timeseries':
                self.__add_data(
                    np.copy(ds['events/event'][channel, use_idx, :]))

            # add also the events and the mainpar seperately
            self.__add_events(ds['events/event'][channel, use_idx, :])
            self.__add_mainpar(
                ds['events/mainpar'][channel, use_idx, :], ds['events/mainpar'].attrs.items())

            # if there are labels in the h5 set then also add them
            if 'labels' in ds['events']:
                # add the labels of all the events
                self.__add_label_nbrs(
                    np.copy(ds['events/labels'][channel, use_idx]))

                # add the colors that correspond to the labels
                if len(np.unique(self.label_nbrs)) > len(self.color_order):
                    print(console_colors.FAIL + "WARNING: " + console_colors.ENDC +
                          "The color_order only contains {} where as there are {} unique labels.".format(
                              len(self.color_order), len(np.unique(self.label_nbrs))))

                # add the namings of the labels
                self.__add_labels(list(ds['events/labels'].attrs.items()))

            # if there are no labels, add the events all as unlabeled
            else:
                self.__add_label_nbrs(['unlabeled'] * nbr_events_added)
                self.__add_labels([('unlabeled', 0)])
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "In the provided hdf5 file are no label_nbrs available an therefore are set to 'unlabeled'.")

            # add a numbering to each event to which file it belongs
            self.__add_file_nbrs(np.full(nbr_events_added, file_index))

            # add a continuous numbering to the events such that they are uniquely identifiable
            self.__add_event_nbrs(
                np.arange(self.events_per_file[file_index], self.events_per_file[file_index] + nbr_events_added))
            # increase the value of the stored counter of the events per file
            self.events_per_file[file_index] += nbr_events_added
            # reset the train_test split variable because new data was added
            self.is_traintest_valid = False

        if verb:
            print('Added Events from file to instance.')

    def set_data(self, data):
        """
        Replaces mainparameters or timeseries with a chosen data set of data.

        :param data: dataset which is analysed
        """

        if data.shape[0] != self.events.shape[0]:
            raise ValueError(console_colors.FAIL + "WARNING: " + console_colors.ENDC +
                             "The the length of data {} does not correspond to the" +
                             " number of events {}.".format(data.shape[0], self.events.shape[0]))

        self.data = data
        self.gen_features()

    def set_scaler(self, scaler):
        """
        Sets the scaler for generating the featuers from the data set.
        Per default the sklearn.preprocessing.StandardScaler() is used.

        :param scaler: scaler for normalizing the data
        """
        if scaler is None:
            self.scaler = StandardScaler()
        else:
            self.scaler = scaler
        self.gen_features()

    def gen_features(self):
        """
        Normalizes the data and saves it into features.
        """
        if type(self.scaler) == type(StandardScaler()):
            self.scaler.fit(self.data)
            self.features = self.scaler.transform(self.data)
        else:
            print("If the StandardScaler is not used the features have to " +
                  "be transformed manually using 'set_features()'.")

    def set_features(self, featuers):
        """
        If not the StandardScaler is used features have to be set manually,
        e.g. by using this function.

        :param features: manual generated features
        """
        featuers = np.array(featuers)
        if self.data.shape != featuers.shape:
            raise ValueError(console_colors.FAIL + "WARNING: " + console_colors.ENDC +
                             "The shape of featuers {}".format(featuers.shape) +
                             " has to be the same as "+
                             "shape of data {}".format(self.data.shape) +
                             ", since they should just be transformed.")
        self.features = featuers


    def add_prediction(self, pred_method, pred, true_labels=False, verb=False):
        """
        Adds a new prediction method with labels to the predictions property.

        :param pred_method: string, the name of the model that made the predictions
        :param path: list of int, contains the predicted labels for the events
        :param true_labels: boolean, default False, set to True when predicted labels correspond to actual label numbers (as in superviced learning methods)
        :param verb: boolean, default False, if True addtional output is printed to the console
        """
        if len(pred) != len(self.label_nbrs):
            raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                             "The parameter 'pred' must have the same amoutn of entries ({}) as " +
                             "events ({}).".format(len(pred), len(self.label_nbrs)))

        if self.predictions is None:
            self.predictions = dict([(pred_method, (true_labels, pred))])
        else:
            if pred_method not in self.predictions.keys():
                self.predictions[pred_method] = (true_labels, pred)
            elif verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "A prediction method with the name '{}' allready exists.".format(pred_method))

        if verb:
            print('Added Predictions to instance.')

    def save_prediction(self, pred_method, path, fname, channel):
        """
        Saves the predictions as a CDV file

        :param pred_method: string, the name of the model that made the predictions
        :param path: string, path to the folder that should contain the predictions
        :param fname: string, the name of the file, e.g. "bck_001"
        :param channel: int, the number of the channel in the module, e.g. Phonon 0, Light 1
        :param verb: boolean, default False, if True  additional ouput is printed
        """
        if self.predictions is None:
            raise AttributeError('Add predictions first!')

        np.savetxt(path + '/' + pred_method + '_predictions_' + fname + '_events_Ch' + str(channel) + '.csv',
                   np.array(self.predictions[pred_method][1]), delimiter='\n')  # the index 1 should access the pred

        print('Saved Predictions as CSV file.')

    def split_test_train(self, test_size, verb=False):
        """
        Seperates the dataset into a training set and a test set with the
        size is determined by the input test_size in percent.

        :param test_size: float in (0,1), size of the test set
        :param verb: boolean, default False, if True additional output is printed
        """
        if test_size <= 0 or test_size >= 1:
            raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                             "The parameter 'test_size' can only have values between 0 and 1.")

        self.test_size = test_size
        total_nbr = np.sum(self.events_per_file)
        event_num = np.arange(total_nbr)
        event_num_train, event_num_test = train_test_split(
            event_num, test_size=test_size)

        self.is_train = np.isin(event_num, event_num_train)
        self.is_traintest_valid = True

        self.gen_features()
        if verb:
            print('Data set splitted.')

    def convert_to_labels(self, label_nbrs, verb=False):
        """
        Converts given label numbers to the corresponding label.

        :param label_nbrs: list of int, contain the label numbers
        :param verb: boolean, default False, if True addtional output is printed to the console
        :return: list of labels which correspond to the label numbers
        """
        unique_label_nbrs = np.unique(label_nbrs)
        if not np.isin(unique_label_nbrs, list(self.labels.keys())).all():
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "Given label numbers contain unkown labels.")
            return None
        return np.array([self.labels[i] for i in label_nbrs])

    def convert_to_colors(self, label_nbrs, verb=False):
        """
        Converts given label numbers into colors for matplotlib.

        :param label_nbrs: list of int, contain the label numbers
        :param verb: boolean, default False, if True addtional output is printed to the console
        :return: list of colors (same color for the same labels)
        """
        unique_label_dict = dict(
            [(l, i) for i, l in enumerate(np.unique(label_nbrs))])
        if len(unique_label_dict) > len(self.color_order):
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "Given label numbers contain more labels than supported colors.")
            return None
        return [self.color_order[unique_label_dict[l]] for l in label_nbrs]

    def convert_to_labels_colors(self, label_nbrs, return_legend=False, verb=False):
        """
        Converts given label numbers into colors for matplotlib.

        :param label_nbrs: list of int, contain the label numbers
        :param return_legend: boolean, default False, if True a legend in format for matplotlib is returned additionally
        :param verb: boolean, default False, if True addtional output is printed to the console
        :return: list of labels, list of colors, optional legend for matplotlib
        """
        labels = self.convert_to_labels(label_nbrs, verb=verb)
        colors = self.convert_to_colors(label_nbrs, verb=verb)

        if return_legend:
            legend = np.unique([labels, label_nbrs, colors], axis=1)
            return labels, colors, legend

        return labels, colors

    # ################### GETTER ###################

    def get_train(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.get_train_event_nbrs(verb=verb), \
            self.get_train_data(verb=verb), \
            self.get_train_features(verb=verb), \
            self.get_train_file_nbrs(verb=verb), \
            self.get_train_label_nbrs(verb=verb)

    def get_test(self, verb=False):
        self.__check_test_set(verb=verb)
        return self.get_test_event_nbrs(verb=verb), \
            self.get_test_data(verb=verb), \
            self.get_test_features(verb=verb), \
            self.get_test_file_nbrs(verb=verb), \
            self.get_test_label_nbrs(verb=verb)

    # ------- get event numbers -------
    def get_train_event_nbrs(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.event_nbrs[self.is_train]

    def get_test_event_nbrs(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.event_nbrs[np.logical_not(self.is_train)]

    def get_event_nbrs(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_event_nbrs(verb=verb)
        elif what == 'test':
            return self.get_test_event_nbrs(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return self.event_nbrs

    # ------- get data -------
    def get_train_data(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.data[self.is_train, :]

    def get_test_data(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.data[np.logical_not(self.is_train)]

    def get_data(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_data(verb=verb)
        elif what == 'test':
            return self.get_test_data(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return self.data

    # ------- get mainparameters -------
    def get_train_mainpar(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.mainpar[self.is_train, :]

    def get_test_mainpar(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.mainpar[np.logical_not(self.is_train)]

    def get_mainpar(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_mainpar(verb=verb)
        elif what == 'test':
            return self.get_test_mainpar(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return self.mainpar

    # ------- get events -------
    def get_train_events(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.events[self.is_train, :]

    def get_test_events(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.events[np.logical_not(self.is_train)]

    def get_events(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_events(verb=verb)
        elif what == 'test':
            return self.get_test_events(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return self.events

    # ------- get features (normalized data) -------
    def get_train_features(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.features[self.is_train]

    def get_test_features(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.features[np.logical_not(self.is_train)]

    def get_features(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_features(verb=verb)
        elif what == 'test':
            return self.get_test_features(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return self.features

    # ------- get file nbrs -------
    def get_train_file_nbrs(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.file_nbrs[self.is_train]

    def get_test_file_nbrs(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.file_nbrs[np.logical_not(self.is_train)]

    def get_file_nbrs(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_file_nbrs(verb=verb)
        elif what == 'test':
            return self.get_test_file_nbrs(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return self.file_nbrs

    # ------- get file nbrs -------
    def get_train_label_nbrs(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.label_nbrs[self.is_train]

    def get_test_label_nbrs(self, verb=False):
        self.__check_train_set(verb=verb)
        return self.label_nbrs[np.logical_not(self.is_train)]

    def get_label_nbrs(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_label_nbrs(verb=verb)
        elif what == 'test':
            return self.get_test_label_nbrs(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return self.label_nbrs

    def get_train_pred_in_color(self, pred_method, verb=False):
        return [self.labels_color_map[i] for i in self.get_train_label_nbrs(verb=verb)]

    def get_test_labels_in_color(self, verb=False):
        return [self.labels_color_map[i] for i in self.get_test_label_nbrs(verb=verb)]

    def get_labels_in_color(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_labels_in_color(verb=verb)
        elif what == 'test':
            return self.get_test_labels_in_color(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return [self.labels_color_map[i] for i in self.get_label_nbrs()]

    # ------- get prediction (predicted label nbrs) -------
    def get_train_pred(self, pred_method, verb=False):
        self.__check_train_set(verb=verb)
        if pred_method not in list(self.predictions.keys()):
            if verb:
                print(console_colors.WARNING + "NOTE: " + console_colors.ENDC +
                      "The prediction method '{}' does not exist in the stored predictions.".format(pred_method))
            return False
        return self.predictions[pred_method][1][self.is_train]

    def get_test_pred(self, pred_method, verb=False):
        self.__check_train_set(verb=verb)
        if pred_method not in list(self.predictions.keys()):
            if verb:
                print(console_colors.WARNING + "NOTE: " + console_colors.ENDC +
                      "The prediction method '{}' does not exist in the stored predictions.".format(pred_method))
            return False
        return self.predictions[pred_method][1][np.logical_not(self.is_train)]

    def get_pred(self, pred_method, what='all', verb=False):
        if what == 'train':
            return self.get_train_pred(pred_method, verb=verb)
        elif what == 'test':
            return self.get_test_pred(pred_method, verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            if pred_method not in list(self.predictions.keys()):
                if verb:
                    print(console_colors.WARNING + "NOTE: " + console_colors.ENDC +
                          "The prediction method '{}' does not exist in the stored predictions.".format(pred_method))
                return False
            return self.predictions[pred_method][1]

    def get_train_pred_in_color(self, pred_method, verb=False):
        self.__check_train_set(verb=verb)
        if pred_method not in list(self.predictions.keys()):
            if verb:
                print(console_colors.WARNING + "NOTE: " + console_colors.ENDC +
                      "The prediction method '{}' does not exist in the stored predictions.".format(pred_method))
            return False
        if self.get_pred_true_labels(pred_method):
            return [self.labels_color_map[i] for i in self.get_train_pred(pred_method, verb=verb)]
        else:
            return [self.color_order[i] for i in self.get_train_pred(pred_method, verb=verb)]

    def get_test_pred_in_color(self, pred_method, verb=False):
        self.__check_train_set(verb=verb)
        if pred_method not in list(self.predictions.keys()):
            if verb:
                print(console_colors.WARNING + "NOTE: " + console_colors.ENDC +
                      "The prediction method '{}' does not exist in the stored predictions.".format(pred_method))
            return False
        if self.get_pred_true_labels(pred_method):
            return [self.labels_color_map[i] for i in self.get_test_pred(pred_method, verb=verb)]
        else:
            return [self.color_order[i] for i in self.get_test_pred(pred_method, verb=verb)]

    def get_pred_in_color(self, pred_method, what='all', verb=False):
        if what == 'train':
            return self.get_train_pred_in_color(pred_method, verb=verb)
        elif what == 'test':
            return self.get_test_pred_in_color(pred_method, verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            if pred_method not in list(self.predictions.keys()):
                if verb:
                    print(console_colors.WARNING + "NOTE: " + console_colors.ENDC +
                          "The prediction method '{}' does not exist in the stored predictions.".format(pred_method))
                return False
            if self.get_pred_true_labels(pred_method):
                return [self.labels_color_map[i] for i in self.get_pred(pred_method, verb=verb)]
            else:
                return [self.color_order[i] for i in self.get_pred(pred_method, verb=verb)]

    # ------- get if prediction labels correspond to the actual labels -------
    def get_pred_true_labels(self, pred_method):
        return self.predictions[pred_method][0]

    # ------- get filepaths -------
    def get_train_filepaths(self, verb=False):
        self.__check_train_set(verb=verb)
        return [self.files[f] for f in self.file_nbrs[self.is_train]]

    def get_test_filepaths(self, verb=False):
        self.__check_train_set(verb=verb)
        return [self.files[f] for f in self.file_nbrs[np.logical_not(self.is_train)]]

    def get_filepaths(self, what='all', verb=False):
        if what == 'train':
            return self.get_train_filepaths(verb=verb)
        elif what == 'test':
            return self.get_test_file_nbrs(verb=verb)
        else:
            if verb and what != 'all':
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'what' is not 'train' or 'test' then all are shown.")
            return [self.files[f] for f in self.file_nbrs]

    # ################### PLOT ###################

    def plt_pred_with_tsne(self, pred_methods, plt_what='all', plt_labels=True,
                           figsize=None, perplexity=30, as_cols=False, rdseed=1,
                           verb=False):
        """
        Plots data with TSNE when given a one or a list of predictions method
        to compare different labels.

        :param pl_channel:      - Required  : Data to be plotted.
        :param x_data:          - Required  : Data to be plotted.
        :param y_pred:          - Required  : Lists of labels.
        :param subtitles:       - Required  : Lists of subtitles.
        :param filepathlist:    - Required  : Lists of paths.
        :param true_labels:     - Optional  : The true labels.
        :param perplexity:      - Optional  : Perplexity for the TSNE.
        :param as_cols:         - Optional  : If true plots are in columns. (Default False)
        :param rdseed:          - Optional  : Random seed for numpy random. (Default 1)
        """
        np.random.seed(seed=rdseed)  # fixing random seed

        if type(pred_methods) is not list and type(pred_methods) is not str:
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "'pred_methods' has to of type list or string.")

        if type(pred_methods) is str:
            pred_methods = [pred_methods]

        for m in pred_methods:
            if m not in self.predictions.keys():
                raise ValueError(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                                 "Prediction method {} is not in the predictions dictionary.\n".format(m) +
                                 "Valid options are: {}".format(self.predictions.keys()))

        nrows = len(pred_methods)
        ncols = 1
        subtitles = [''] * nrows

        if plt_labels:
            subtitles = ['Labels'] + pred_methods
            nrows = nrows + 1  # take the true labels into account

        # switch rows and cols
        if as_cols:
            temp = nrows
            nrows = ncols
            ncols = temp

        if plt_what not in ['all', 'test', 'train']:
            plt_what = 'all'
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "If the value of 'plt_what' is not 'train' or 'test' then all are shown.")

        # -------- MATPLOTLIB event handler --------

        def update_annot(ind):
            for i in range(nrows * ncols):
                pos = sc[i].get_offsets()[ind['ind'][0]]
                annot[i].xy = pos
                if ind['ind'].size == 1:
                    id = ind['ind'][0]

                    text = "{}, {}".format(self.files[self.get_file_nbrs(plt_what)[id]].split('/')[-1].split('-')[0],
                                           self.get_event_nbrs(plt_what)[id])
                    if plt_labels:
                        text = text + \
                            ", {}".format(
                                self.labels[self.get_label_nbrs(plt_what, verb=verb)[id]])
                else:
                    text = "{}".format(
                        " ".join(list(map(str, [self.get_event_nbrs(plt_what)[id] for id in ind['ind']]))))
                annot[i].set_text(text)
                annot[i].get_bbox_patch().set_alpha(0.7)

        def hover(event):
            for i in range(nrows * ncols):
                vis = annot[i].get_visible()
                if event.inaxes == ax[i]:
                    # cont: bool, whether it contains something or not
                    cont, ind = sc[i].contains(event)
                    # print(ind)
                    if cont:
                        update_annot(ind)
                        annot[i].set_visible(True)
                        fig.canvas.draw_idle()
                    else:
                        if vis:
                            annot[i].set_visible(False)
                            fig.canvas.draw_idle()

        def onclick(event):
            for i in range(nrows * ncols):
                if event.inaxes == ax[i]:
                    cont, ind = sc[i].contains(event)
                    if ind['ind'].size > 1:
                        print('Select a single event.')
                    elif ind['ind'].size == 1:
                        id = ind['ind'][0]

                        text = "{}, {}".format(
                            self.files[self.get_file_nbrs(plt_what, verb=verb)[
                                id]].split('/')[-1].split('-')[0],
                            self.get_event_nbrs(plt_what, verb=verb)[id])
                        if plt_labels:
                            text = text + ", {} = {}".format(self.labels[self.get_label_nbrs(plt_what, verb=verb)[id]],
                                                             self.get_label_nbrs(plt_what, verb=verb)[id])

                        print("Plotting Event nbr. '{}' from file '{}'.".format(
                            self.get_event_nbrs(plt_what, verb=verb)[id],
                            self.files[self.get_file_nbrs(plt_what, verb=verb)[id]]))
                        instr = "python3 pltSingleEvent.py {} {} '{}' -T '{}' &".format(self.pl_channel, self.get_event_nbrs(
                            plt_what, verb=verb)[id], self.files[self.get_file_nbrs(plt_what, verb=verb)[id]], text)
                        print(instr)
                        os.system(instr)

        def on_key(event):
            if event.key == 'm':
                for i in range(nrows * ncols):
                    if event.inaxes == ax[i]:
                        cont, ind = sc[i].contains(event)
                        if ind['ind'].size > 1:
                            print('Select a single event.')
                        elif ind['ind'].size == 1:
                            id = ind['ind'][0]

                            text = "{}, {}".format(
                                self.files[self.get_file_nbrs(plt_what, verb=verb)[
                                    id]].split('/')[-1].split('-')[0],
                                self.get_event_nbrs(plt_what, verb=verb)[id])
                            if plt_labels:
                                text = text + ", {} = {}".format(
                                    self.labels[self.get_label_nbrs(
                                        plt_what, verb=verb)[id]],
                                    self.get_label_nbrs(plt_what, verb=verb)[id])

                            print("Plotting Event nbr. '{}' from file '{}'.".format(
                                self.get_event_nbrs(plt_what, verb=verb)[id],
                                self.files[self.get_file_nbrs(plt_what, verb=verb)[id]]))
                            instr = "python3 pltSingleEvent.py {} {} '{}' -m -T '{}' &".format(self.pl_channel, self.get_event_nbrs(
                                plt_what, verb=verb)[id], self.files[self.get_file_nbrs(plt_what, verb=verb)[id]], text)
                            os.system(instr)
            elif event.key == 'p':
                for i in range(nrows * ncols):
                    if event.inaxes == ax[i]:
                        cont, ind = sc[i].contains(event)
                        if ind['ind'].size > 1:
                            print('Select a single event.')
                        elif ind['ind'].size == 1:
                            id = ind['ind'][0]
                            import ipdb
                            ipdb.set_trace()

        if not self.save_pgf:
            print(
                "-------------------------------------------------------------------------")
            print('Hovering over an event shows you the event number.')
            print(
                'When clicking on a single event a window with its timeseries is opened.')
            print(
                "Hovering over a a single event and pressing 'm' also opnes the timeseries")
            print("of this event and adds the calculated mainparameters to the plot.")
            print(
                "-------------------------------------------------------------------------")

        # -------- PLOT --------
        # PCA
        # pca = PCA(n_components=2)
        # princcomp = pca.fit_transform(x_data)

        # TSNE
        princcomp = TSNE(n_components=2, perplexity=perplexity).fit_transform(
            self.get_features(plt_what, verb=verb))

        if self.save_pgf:
            set_mpl_backend_pgf()

        if type(figsize) is not tuple:
            fig, ax = plt.subplots(
                nrows=nrows, ncols=ncols, sharex=True, sharey=True)
        else:
            fig, ax = plt.subplots(
                nrows=nrows, ncols=ncols, figsize=figsize, sharex=True, sharey=True)

        annot = [None] * nrows * ncols
        sc = [None] * nrows * ncols

        if nrows * ncols == 1:
            ax = [ax]

        start_i = 0
        if plt_labels:
            start_i = 1
            ax[0].set_title(subtitles[0])
            _, _, leg = self.convert_to_labels_colors(self.get_label_nbrs(plt_what, verb=verb), return_legend=True,
                                                      verb=verb)

            if self.save_pgf:
                sc[0] = ax[0].scatter(princcomp[:, 0], princcomp[:, 1],
                                      c=self.get_labels_in_color(what=plt_what, verb=verb), s=2, alpha=0.7)
            else:
                sc[0] = ax[0].scatter(princcomp[:, 0], princcomp[:, 1],
                                      c=self.get_labels_in_color(what=plt_what, verb=verb), s=5, alpha=0.7)
            pop = [None] * leg.shape[1]
            for i in range(leg.shape[1]):
                # pop[i] = mpl.patches.Patch(color=leg[2,i], label="{} ({})".format(leg[1,i], leg[0,i]))
                pop[i] = mpl.patches.Patch(
                    color=leg[2, i], label="{} ({})".format(leg[0, i], leg[1, i]))
            ax[0].legend(handles=pop, framealpha=0.3)

        # import ipdb; ipdb.set_trace()
        for i in range(start_i, nrows * ncols):
            ax[i].set_title(subtitles[i])

            if self.save_pgf:
                sc[i] = ax[i].scatter(princcomp[:, 0],
                                      princcomp[:, 1],
                                      c=self.get_pred_in_color(pred_methods[i - start_i],
                                                               what=plt_what, verb=verb),
                                      s=2,
                                      alpha=0.7)
            else:
                sc[i] = ax[i].scatter(princcomp[:, 0],
                                      princcomp[:, 1],
                                      c=self.get_pred_in_color(pred_methods[i - start_i],
                                                               what=plt_what, verb=verb),
                                      s=5,
                                      alpha=0.7)

        for i in range(nrows * ncols):
            annot[i] = ax[i].annotate("", xy=(0, 0), xytext=(20, 20), textcoords="offset points",
                                      bbox=dict(boxstyle="round", fc="w"),
                                      arrowprops=dict(arrowstyle="->"))
            annot[i].set_visible(False)

        if self.save_pgf:
            if plt_labels:
                plt.gcf().subplots_adjust(top=0.95, right=0.5)
                ax[0].legend(handles=pop, framealpha=0.3,
                             loc='center left', bbox_to_anchor=(1.0, 0.5))

            set_mpl_backend_fontsize(10)
            if pred_methods == [] and plt_labels:
                plt.savefig(
                    '{}tsne-{}.pgf'.format(self.save_plot_dir, 'labels'))
            else:
                plt.savefig(
                    '{}tsne-{}.pgf'.format(self.save_plot_dir, '_'.join(pred_methods)))
        else:
            fig.canvas.mpl_connect('key_press_event', on_key)
            fig.canvas.mpl_connect("motion_notify_event", hover)
            fig.canvas.mpl_connect('button_press_event', onclick)

            plt.show()
        plt.close()

    def pulse_height_histogram(self,
                               ncols=2,
                               extend_plot=False,
                               figsize=None,
                               bins='auto',
                               verb=False):
        """
        Plots a histogram for all labels of the pulse hights in different
        subplots.

        :param ncols:           - optional, default 2 : number of plots side by side.
        :param extend_plot:     - optional, default False : sets the x axis of all histograms to the same limits.
        :param figsize:         - optional, default None : changes the overall figure size.
        :param bins:            - optional, default auto : bins for the histograms.
        :param verb:            - optional, default False : ouputs additional information.
        """
        max_height = self.get_mainpar(
            verb=verb)[:, self.mainpar_labels['pulse_height']]

        max_max_height = np.max(max_height)
        min_max_height = np.min(max_height)

        unique_label_nbrs = np.unique(self.get_label_nbrs(verb=verb))
        max_height_per_label = dict(
            [(l, max_height[self.get_label_nbrs(verb=verb) == l]) for l in unique_label_nbrs])

        nrows = math.ceil(len(unique_label_nbrs) / ncols)

        fig, ax = plt.subplots(nrows=nrows, ncols=ncols)

        for i, l in enumerate(unique_label_nbrs):
            j = i % ncols
            k = int(i / ncols)
            # print("i ({}); j ({}); k ({})".format(i,j,k))
            if k * ncols + j > i:
                break
            ax[k][j].set_title(self.labels[l])
            ax[k][j].hist(max_height_per_label[l], bins=bins)

        fig.tight_layout()
        if extend_plot:
            for i, l in enumerate(unique_label_nbrs):
                j = i % ncols
                k = int(i / ncols)
                # print("i ({}); j ({}); k ({})".format(i,j,k))
                if k * ncols + j > i:
                    break
                ax[k][j].set_xlim(min_max_height, max_max_height)

        if self.save_pgf:

            plt.savefig('{}labels_dist.pgf'.format(self.save_plot_dir))
        else:
            plt.show()
        plt.close()

    def events_saturated_histogram(self, figsize=None, bins='auto', verb=False, ylog=False):
        """
        Plots a histogram for all event pulses and strongly saturated event pulses
        in a single plot.

        :param figsize:         - optional, default None : changes the overall figure size.
        :param bins:            - optional, default auto : bins for the histograms.
        :param ylog:            - optional, default False : if True the y axis is in log scale.
        """
        if self.save_pgf:
            # set_mpl_backend_pgf()
            mpl.use('pdf')

        max_height = self.get_mainpar(
            verb=verb)[:, self.mainpar_labels['pulse_height']]

        unique_label_nbrs = np.unique(self.get_label_nbrs(verb=verb))
        max_height_per_label = dict(
            [(l, max_height[self.get_label_nbrs(verb=verb) == l]) for l in unique_label_nbrs])

        for i, l in self.labels.items():
            if l == 'Event_Pulse':
                events_nbr = i
            if l == 'Strongly_Saturated_Event_Pulse':
                saturated_nbr = i

        fig, ax = plt.subplots(figsize=figsize, tight_layout=True)

        ax.hist([max_height_per_label[events_nbr], max_height_per_label[saturated_nbr]],
                label=['{}'.format(self.labels[events_nbr]),
                       '{}'.format(self.labels[saturated_nbr])],
                bins=bins)

        ax.set_xlabel('pulse height [V]')
        ax.set_ylabel('number of events')

        plt.legend()
        if ylog:
            ax.set_yscale('log')
        if self.save_pgf:
            if ylog:
                plt.savefig(
                    '{}evt_sat_hist-ylog.pdf'.format(self.save_plot_dir))
            else:
                plt.savefig('{}evt_sat_hist.pdf'.format(self.save_plot_dir))
        else:
            plt.show()
        plt.close()

    def correctly_labeled_per_v(self, pred_method, what='all', bin_size=4, ncols=2, extend_plot=False, verb=False):
        """
        Plots the number of correctly predicted labels over volts (pulse height)
        for every label.

        :param pred_method:     - Required : Name of the predictions method.
        :param what:            - Optional, default all : test or train data or all.
        :param bin_size:        - Optional, default 4 : bin size for calculating the average.
        :param ncols:           - Optional, default 2 : number of plots side by side.
        :param extend_plot:     - Optional, default False : if True x limits is set to the same for all subplots.
        :param verb:            - Optional, default False : if True additional information is printed on the console.
        """
        if self.save_pgf:
            set_mpl_backend_pgf()

        if type(pred_method) is not str:
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "'pred_methods' has to of type string.")
            return None

        if pred_method not in self.predictions.keys():
            raise ValueError(console_colors.FAIL + "FAILED: " + console_colors.ENDC +
                             "Prediction method {} is not in the predictions dictionary.\n".format(pred_method) +
                             "Valid options are: {}".format(self.predictions.keys()))

        if not self.get_pred_true_labels(pred_method):
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "Only prediction methods with the same labeling as the" +
                      "correct labels are supported by this function.")
            return

        max_height = self.get_mainpar(what, verb=verb)[
            :, self.mainpar_labels['pulse_height']]

        max_max_height = np.max(max_height)
        min_max_height = np.min(max_height)

        unique_label_nbrs, unique_label_counts = np.unique(
            self.get_label_nbrs(what, verb=verb), return_counts=True)
        data_dict_sorted = dict(
            [(l, ([None] * c, [None] * c, [None] * c)) for l, c in zip(unique_label_nbrs, unique_label_counts)])

        pos_counter = dict([(l, 0) for l in unique_label_nbrs])

        for h, tl, pl in sorted(
                zip(max_height, self.get_label_nbrs(what, verb=verb), self.get_pred(pred_method, what, verb=verb))):
            data_dict_sorted[tl][0][pos_counter[tl]] = h
            data_dict_sorted[tl][1][pos_counter[tl]] = pl
            pos_counter[tl] += 1

        for l in unique_label_nbrs:
            pl = np.array(data_dict_sorted[l][1])
            pl[pl != l] = 0
            pl[pl == l] = 1
            # pl = pl/pl.shape[0]
            # pl = np.cumsum(pl).tolist()
            for i, c in enumerate(pl):
                data_dict_sorted[l][2][i] = c

        bin_boundries = {}
        for l in unique_label_nbrs:
            bins = math.ceil(len(data_dict_sorted[l][2]) / bin_size)
            bin_boundries[l] = ([None] * bins, [None] * bins)
            for i in range(bins):
                upper = (i + 1) * bin_size if (i + 1) * bin_size < len(data_dict_sorted[l][2]) else len(
                    data_dict_sorted[l][2])
                lower = i * bin_size
                bin_boundries[l][0][i] = np.mean(
                    data_dict_sorted[l][0][lower:upper])
                bin_boundries[l][1][i] = np.mean(
                    data_dict_sorted[l][2][lower:upper])

        # import ipdb; ipdb.set_trace()
        nrows = math.ceil(len(unique_label_nbrs) / ncols)
        fig, ax = plt.subplots(nrows=nrows, ncols=ncols)
        for i, l in enumerate(unique_label_nbrs):
            j = i % ncols
            k = int(i / ncols)
            if k * ncols + j > i:
                break
            ax[k][j].set_title(self.labels[l])
            # ax[k][j].hist(data_dict_sorted[l][0],
            #               bins=bin_boundries[l][0])
            if extend_plot:
                ax[k][j].plot([min_max_height] + bin_boundries[l][0] + [max_max_height],
                              [0] + bin_boundries[l][1] + [bin_boundries[l][1][-1]])
            else:
                ax[k][j].plot(bin_boundries[l][0],
                              bin_boundries[l][1])

        plt.xlable('pulse height [V]')
        plt.ylable('accuray')
        plt.show()

    def correctly_labeled_events_per_pulse_height(self, pred_method, what='all',
                                                  bin_size=4, ncols=2, extend_plot=False,
                                                  figsize=None, verb=False):
        """
        Plots the number of correctly predicted labels over volts (pulse height)
        for events.

        :param pred_method:     - Required : Name of the predictions method.
        :param what:            - Optional, default all : test or train data or all.
        :param bin_size:        - Optional, default 4 : bin size for calculating the average.
        :param ncols:           - Optional, default 2 : number of plots side by side.
        :param extend_plot:     - Optional, default False : if True x limits is set to the same for all subplots.
        :param figsize:         - optional, default None : changes the overall figure size.
        :param verb:            - Optional, default False : if True additional information is printed on the console.
        """
        if self.save_pgf:
            set_mpl_backend_pgf()

        if type(pred_method) is not str:
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "'pred_methods' has to of type string.")
            return None

        if pred_method not in self.predictions.keys():
            raise ValueError(console_colors.FAIL + "FAILED: " + console_colors.ENDC +
                             "Prediction method {} is not in the predictions dictionary.\n".format(pred_method) +
                             "Valid options are: {}".format(self.predictions.keys()))

        if not self.get_pred_true_labels(pred_method):
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "Only prediction methods with the same labeling as the" +
                      "correct labels are supported by this function.")
            return

        max_height = self.get_mainpar(what, verb=verb)[
            :, self.mainpar_labels['pulse_height']]

        max_max_height = np.max(max_height)
        min_max_height = np.min(max_height)

        unique_label_nbrs, unique_label_counts = np.unique(
            self.get_label_nbrs(what, verb=verb), return_counts=True)
        data_dict_sorted = dict(
            [(l, ([None] * c, [None] * c, [None] * c)) for l, c in zip(unique_label_nbrs, unique_label_counts)])

        pos_counter = dict([(l, 0) for l in unique_label_nbrs])

        for h, tl, pl in sorted(
                zip(max_height, self.get_label_nbrs(what, verb=verb), self.get_pred(pred_method, what, verb=verb))):
            data_dict_sorted[tl][0][pos_counter[tl]] = h
            data_dict_sorted[tl][1][pos_counter[tl]] = pl
            pos_counter[tl] += 1

        for l in unique_label_nbrs:
            pl = np.array(data_dict_sorted[l][1])
            pl[pl != l] = 0
            pl[pl == l] = 1
            # pl = pl/pl.shape[0]
            # pl = np.cumsum(pl).tolist()
            for i, c in enumerate(pl):
                data_dict_sorted[l][2][i] = c

        bin_boundries = {}
        for l in unique_label_nbrs:
            bins = math.ceil(len(data_dict_sorted[l][2]) / bin_size)
            bin_boundries[l] = ([None] * bins, [None] * bins)
            for i in range(bins):
                upper = (i + 1) * bin_size if (i + 1) * bin_size < len(data_dict_sorted[l][2]) else len(
                    data_dict_sorted[l][2])
                lower = i * bin_size
                bin_boundries[l][0][i] = np.mean(
                    data_dict_sorted[l][0][lower:upper])
                bin_boundries[l][1][i] = np.mean(
                    data_dict_sorted[l][2][lower:upper])

        # import ipdb; ipdb.set_trace()

        l = 1  # events
        # nrows = math.ceil(len(unique_label_nbrs)/ncols)
        if figsize is None:
            fig, ax = plt.subplots(nrows=1, ncols=1)
        else:
            fig, ax = plt.subplots(nrows=1, ncols=1, figsize=figsize)
        ax.set_title(self.labels[l])
        # ax[k][j].hist(data_dict_sorted[l][0],
        #               bins=bin_boundries[l][0])
        ax.plot(bin_boundries[l][0],
                bin_boundries[l][1])

        ax.set_xlabel('pulse height [V]')
        ax.set_ylabel('accuray')
        ax.set_xlim(0, 0.2)
        # plt.gcf().subplots_adjust(bottom=-0.1)
        if self.save_pgf:
            plt.savefig(
                '{}correctly_labeled_events-{}.pgf'.format(self.save_plot_dir, pred_method))
        else:
            plt.show()
        plt.close()

    def confusion_matrix_pred(self, pred_method, what='all', rotation_xticklabels=0,
                              force_xlabelnbr=False, figsize=None, verb=False):
        """
        Plots a confusion matrix to better visualize which labels are better
        predicted by a certain prediction method.
        In the (i,j) position the number of i labels which are predicted a j
        are written.
        When clicking on a matrix element the event number and from which file
        is printed out in the console

        :param pred_method:         - Required : Name of the predictions method.
        :param what:                - Optional, default all : test or train data or all.
        :param rotation_xticklabels:- Optional, default 0 : lets you rotate the x tick labels.
        :param force_xlabelnbr:     - Optional, default False : uses the number instead of the labels for better readability.
        :param figsize:             - optional, default None : changes the overall figure size.
        :param verb:                - Optional, default False : if True additional information is printed on the console.
        """

        if self.save_pgf:
            set_mpl_backend_pgf()

        if type(pred_method) is not str:
            if verb:
                print(console_colors.OKBLUE + "NOTE: " + console_colors.ENDC +
                      "'pred_methods' has to of type string.")
            return None

        if pred_method not in self.predictions.keys():
            raise ValueError(console_colors.FAIL + "ERROR: " + console_colors.ENDC +
                             "Prediction method {} is not in the predictions dictionary.\n".format(pred_method) +
                             "Valid options are: {}".format(self.predictions.keys()))

        ylabels_order = [self.labels[l] + " ({})".format(l)
                         for l in np.unique(self.get_label_nbrs(what, verb=verb))]

        if self.get_pred_true_labels(pred_method):
            xlabels_order = ylabels_order
        else:
            xlabels_order = np.unique(
                self.get_pred(pred_method, what, verb=verb))

        diff = len(ylabels_order) - len(xlabels_order)
        for i in range(abs(diff)):
            if diff > 0:  # len(ylabels_order)>len(xlabels_order)
                xlabels_order.append(chr(ord('a') + i))
            elif diff < 0:  # len(ylabels_order)<len(xlabels_order)
                ylabels_order.append(chr(ord('a') + i))

        pred_labels = self.get_pred(pred_method, what, verb=verb)
        if not self.get_pred_true_labels(pred_method):
            pred_labels_dict = dict(
                [(pl, tl) for tl, pl in zip(np.unique(self.get_label_nbrs(what, verb=verb)), xlabels_order)])
            pred_labels = [pred_labels_dict[l] for l in pred_labels]

        if self.get_pred_true_labels(pred_method) and force_xlabelnbr:
            xlabels_order = [l.split(')')[0] for l in [l.split(
                '(')[-1] for l in xlabels_order]]

        if type(xlabels_order) is np.ndarray:
            xlabels_order = xlabels_order.tolist()
        if type(ylabels_order) is np.ndarray:
            ylabels_order = ylabels_order.tolist()
        cm = confusion_matrix(self.get_label_nbrs(what, verb=verb),
                              self.get_pred(pred_method, what, verb=verb))
        if verb:
            print(cm)

        if self.save_pgf:
            set_mpl_backend_pgf()

        def onclick(event):
            if event.inaxes == ax:
                cont, ind = cax.contains(event)

                x = event.xdata
                y = event.ydata
                i = int(y + 0.5)
                j = int(x + 0.5)

                selected_label_nbr = np.unique(
                    self.get_label_nbrs(verb=verb))[i]
                if self.get_pred_true_labels(pred_method):
                    selected_pred_nbr = np.unique(
                        self.get_label_nbrs(verb=verb))[j]
                else:
                    selected_pred_nbr = np.unique(
                        self.get_pred(pred_method, verb=verb))[j]

                selection = np.logical_and(self.get_label_nbrs(what, verb) == selected_label_nbr,
                                           self.get_pred(pred_method, what, verb) == selected_pred_nbr)
                # import ipdb; ipdb.set_trace()
                results = [
                    self.get_file_nbrs(what, verb)[selection],
                    self.get_event_nbrs(what, verb)[selection],
                    self.get_label_nbrs(what, verb)[selection],
                    self.get_pred(pred_method, what, verb)[selection]
                ]
                # import ipdb; ipdb.set_trace()
                print("---------- Events labeled as {} ({}) but predicted as {} ----------".format(
                    self.labels[selected_label_nbr], selected_label_nbr, selected_pred_nbr))
                for fn, en, ln, pn in zip(*results):
                    print("'{}' \t Event_nbr:{:>4} \t Label:{:>3}, \t Prediction:{:>3}".format(self.files[fn], en, ln,
                                                                                               pn))
                print("--------------------")
                print()

        if type(figsize) is not tuple:
            fig = plt.figure()
        else:
            fig = plt.figure(figsize=figsize)

        ax = fig.add_subplot(111)

        cax = ax.matshow(cm, cmap='plasma', alpha=0.7)
        # plt.title('Confusion matrix of the classifier')
        fig.colorbar(cax)

        if ylabels_order != []:
            ax.set_yticks(np.arange(len(ylabels_order)))
            ax.set_yticklabels(ylabels_order)

        if xlabels_order != []:
            ax.set_xticks(np.arange(len(xlabels_order)))
            ax.set_xticklabels(xlabels_order,
                               rotation=rotation_xticklabels)

        plt.gcf().subplots_adjust(left=0.5)

        for (i, j), z in np.ndenumerate(cm):
            ax.text(j, i, '{:0.1f}'.format(z), ha='center', va='center')

        ax.yaxis.set_label_position('right')
        plt.xlabel('Predicted Labels')
        plt.ylabel('Labels')
        fig.tight_layout()
        if not self.save_pgf:
            fig.canvas.mpl_connect('button_press_event', onclick)
            plt.show()
        else:
            plt.savefig(
                '{}confMat-{}.pgf'.format(self.save_plot_dir, pred_method))

        plt.close()

    def plot_labels_distribution(self, figsize=None):
        """
        Uses a bar graph to visualize how often a label occures in the
        dataset

        :param figsize:             - optional, default None : changes the overall figure size.
        """
        if self.save_pgf:
            set_mpl_backend_pgf()

        lnbr, lcnt = np.unique(self.label_nbrs, return_counts=True)
        lenum = np.arange(lnbr.shape[0])

        if type(figsize) is not tuple:
            fig, ax = plt.subplots()
        else:
            fig, ax = plt.subplots(figsize=figsize)

        bars = plt.bar(lenum, lcnt)
        for i, b in enumerate(bars):
            b.set_color(self.color_order[i])
        plt.xticks(lenum, lnbr)

        rects = ax.patches
        for rect, i in zip(rects, lcnt):
            height = rect.get_height()
            ax.text(rect.get_x() + rect.get_width() / 2, height + 15, i,
                    ha='center', va='bottom')
        bottom, top = plt.ylim()
        plt.ylim(0, 1.1 * top)

        ax.set_ylabel("number of events")
        ax.set_xlabel("labels")

        pop = [None] * len(lnbr)
        for i, j in enumerate(lnbr):
            pop[i] = mpl.patches.Patch(color=self.color_order[i],
                                       label="{} ({})".format(self.labels[j], j))
        ax.legend(handles=pop, framealpha=0.3,
                  loc='center left', bbox_to_anchor=(1.0, 0.5))

        plt.gcf().subplots_adjust(right=0.5)
        if self.save_pgf:
            plt.savefig('{}labels_dist.pgf'.format(self.save_plot_dir))
        else:
            plt.show()
        plt.close()