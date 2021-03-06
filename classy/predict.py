"""
.. py:module:: classy.predict
   :synopsis: Predict text labels using a model and vocabulary.

.. moduleauthor:: Florian Leitner <florian.leitner@gmail.com>
.. License: GNU Affero GPL v3 (http://www.gnu.org/licenses/agpl.html)
"""

import logging
import sys
from classy.generate import fix_column_offset
from sklearn.externals import joblib
from .data import load_index, get_n_rows, load_vocabulary
from .extract import row_generator, row_generator_from_file
from .transform import FeatureEncoder, transform_input


L = logging.getLogger(__name__)


def predict_labels(args):
    L.debug("%s", args)

    if args.text:
        stream_predictor(args)
    else:
        batch_predictor(args)


def batch_predictor(args):
    if not args.index:
        raise ValueError('missing input data file (inverted index)')
    elif len(args.index) > 1:
        raise ValueError('more than one input data file (inverted index)')

    data = load_index(args.index[0])
    pipeline = joblib.load(args.model)
    predictions = pipeline.predict(data.index.tocsr())
    scores = get_scores(pipeline, data) if args.scores else None
    text_ids = get_or_make_text_ids(data)
    make_label = str

    if args.label:
        n_labels = len(args.label)
        make_label = lambda i: (args.label[i] if i < n_labels else i)

    if args.scores:
        report_with_scores(predictions, scores, text_ids, make_label)
    else:
        report_labels(predictions, text_ids, make_label)


def report_labels(predictions, text_ids, make_label):
    for text_id, prediction in zip(text_ids, predictions):
        print(text_id, make_label(prediction), sep='\t')


def report_with_scores(predictions, scores, text_ids, make_label):
    for text_id, prediction, i_scores in \
            zip(text_ids, predictions, scores):
        if isinstance(i_scores, float):
            i_scores = (i_scores,)

        score_str = '\t'.join('{: 0.8f}'.format(s) for s in i_scores)

        print(text_id, make_label(prediction), score_str, sep='\t')


def get_scores(pipeline, data):
    try:
        return pipeline.predict_proba(data.index.tocsr())
    except AttributeError:  # svm and others do not have proba
        return pipeline.decision_function(data.index.tocsr())


def get_or_make_text_ids(data):
    if data.text_ids:
        text_ids = data.text_ids
    else:
        text_ids = range(1, get_n_rows(data) + 1)
    return text_ids


def stream_predictor(args):
    if args.vocabulary is None:
        raise ValueError(
            'missing required option for text input: --vocabulary VOCAB'
        )

    vocabulary = load_vocabulary(args.vocabulary)
    dialect = 'excel' if args.csv else 'plain'
    args.annotate = fix_column_offset(args.annotate)
    args.feature = fix_column_offset(args.feature)

    if not args.index:
        gen = row_generator(sys.stdin, dialect=dialect)
        predict_from(gen, args, vocabulary)
    else:
        for file in args.index:
            gen = row_generator_from_file(file, dialect=dialect,
                                          encoding=args.encoding)
            predict_from(gen, args, vocabulary)


def predict_from(text, args, vocab):
    stream = transform_input(text, args)
    id_col = find_id_col(args)
    stream = FeatureEncoder(stream, vocabulary=vocab,
                            id_col=id_col, label_col=None)
    pipeline = joblib.load(args.model)
    make_label = str
    here = '\t' if args.scores else '\n'  # append score or not
    no_proba = False

    if args.label:
        n_labels = len(args.label)
        make_label = lambda i: args.label[i] if i < n_labels else i

    for text_id, features in stream:
        prediction = pipeline.predict(features)
        assert prediction.shape[0] == 1, "not a single prediction: %s" % str(
            prediction.shape
        )
        print(text_id, make_label(prediction[0]), sep='\t', end=here)

        if args.scores:
            append_scores(pipeline, features, no_proba)


def append_scores(pipeline, features, no_proba):
    if no_proba:
        scores = pipeline.decision_function(features)[0]
    else:
        try:
            scores = pipeline.predict_proba(features)[0]
        except AttributeError:  # svm and other do not have this
            scores = pipeline.decision_function(features)[0]
            no_proba = True
    if isinstance(scores, float):
        scores = (scores,)
    print('\t'.join('{: 0.8f}'.format(s) for s in scores))


def find_id_col(args):
    if args.no_id:
        id_col = None
    elif args.id_second:
        id_col = 1
    elif args.id_last:
        id_col = -1
    else:
        id_col = 0
    return id_col
