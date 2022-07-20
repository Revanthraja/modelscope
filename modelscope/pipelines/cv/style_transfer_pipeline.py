import os.path as osp
from typing import Any, Dict

import cv2
import numpy as np
import PIL

from modelscope.metainfo import Pipelines
from modelscope.outputs import OutputKeys
from modelscope.pipelines.base import Input, Pipeline
from modelscope.pipelines.builder import PIPELINES
from modelscope.preprocessors import load_image
from modelscope.utils.constant import ModelFile, Tasks
from modelscope.utils.logger import get_logger

logger = get_logger()


@PIPELINES.register_module(
    Tasks.style_transfer, module_name=Pipelines.style_transfer)
class StyleTransferPipeline(Pipeline):

    def __init__(self, model: str):
        """
        use `model` and `preprocessor` to create a kws pipeline for prediction
        Args:
            model: model id on modelscope hub.
        """
        super().__init__(model=model)
        import tensorflow as tf
        if tf.__version__ >= '2.0':
            tf = tf.compat.v1
        model_path = osp.join(self.model, ModelFile.TF_GRAPH_FILE)

        config = tf.ConfigProto(allow_soft_placement=True)
        config.gpu_options.allow_growth = True
        self._session = tf.Session(config=config)
        self.max_length = 800
        with self._session.as_default():
            logger.info(f'loading model from {model_path}')
            with tf.gfile.FastGFile(model_path, 'rb') as f:
                graph_def = tf.GraphDef()
                graph_def.ParseFromString(f.read())
                tf.import_graph_def(graph_def, name='')

                self.content = tf.get_default_graph().get_tensor_by_name(
                    'content:0')
                self.style = tf.get_default_graph().get_tensor_by_name(
                    'style:0')
                self.output = tf.get_default_graph().get_tensor_by_name(
                    'stylized_output:0')
                self.attention = tf.get_default_graph().get_tensor_by_name(
                    'attention_map:0')
                self.inter_weight = tf.get_default_graph().get_tensor_by_name(
                    'inter_weight:0')
                self.centroids = tf.get_default_graph().get_tensor_by_name(
                    'centroids:0')
            logger.info('load model done')

    def _sanitize_parameters(self, **pipeline_parameters):
        return pipeline_parameters, {}, {}

    def preprocess(self, content: Input, style: Input) -> Dict[str, Any]:
        if isinstance(content, str):
            content = np.array(load_image(content))
        elif isinstance(content, PIL.Image.Image):
            content = np.array(content.convert('RGB'))
        elif isinstance(content, np.ndarray):
            if len(content.shape) == 2:
                content = cv2.cvtColor(content, cv2.COLOR_GRAY2BGR)
            content = content[:, :, ::-1]  # in rgb order
        else:
            raise TypeError(
                f'modelscope error: content should be either str, PIL.Image,'
                f' np.array, but got {type(content)}')
        if len(content.shape) == 2:
            content = cv2.cvtColor(content, cv2.COLOR_GRAY2BGR)
        content_img = content.astype(np.float)

        if isinstance(style, str):
            style_img = np.array(load_image(style))
        elif isinstance(style, PIL.Image.Image):
            style_img = np.array(style.convert('RGB'))
        elif isinstance(style, np.ndarray):
            if len(style.shape) == 2:
                style_img = cv2.cvtColor(style, cv2.COLOR_GRAY2BGR)
            style_img = style_img[:, :, ::-1]  # in rgb order
        else:
            raise TypeError(
                f'modelscope error: style should be either str, PIL.Image,'
                f' np.array, but got {type(style)}')

        if len(style_img.shape) == 2:
            style_img = cv2.cvtColor(style_img, cv2.COLOR_GRAY2BGR)
        style_img = style_img.astype(np.float)

        result = {'content': content_img, 'style': style_img}
        return result

    def forward(self, input: Dict[str, Any]) -> Dict[str, Any]:
        content_feed, style_feed = input['content'], input['style']
        h = np.shape(content_feed)[0]
        w = np.shape(content_feed)[1]
        if h > self.max_length or w > self.max_length:
            if h > w:
                content_feed = cv2.resize(
                    content_feed,
                    (int(self.max_length * w / h), self.max_length))
            else:
                content_feed = cv2.resize(
                    content_feed,
                    (self.max_length, int(self.max_length * h / w)))

        with self._session.as_default():
            feed_dict = {
                self.content: content_feed,
                self.style: style_feed,
                self.inter_weight: 1.0
            }
            output_img = self._session.run(self.output, feed_dict=feed_dict)

            # print('out_img shape:{}'.format(output_img.shape))
            output_img = cv2.cvtColor(output_img[0], cv2.COLOR_RGB2BGR)
            output_img = np.clip(output_img, 0, 255).astype(np.uint8)

            output_img = cv2.resize(output_img, (w, h))

            return {OutputKeys.OUTPUT_IMG: output_img}

    def postprocess(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return inputs
