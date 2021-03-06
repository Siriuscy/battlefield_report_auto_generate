import pandas as pd
import numpy as np
from generate_background_info import constants
from generate_background_info.utils import functions_utils
import math
import os
import json
import requests
from io import BytesIO
from PIL import Image
import cv2


def get_useful_space_info(bg_id):
    useful_space_data = pd.read_csv(constants.LABEL_BOX_DATASET_PATH)
    img = cv2.imread(os.path.join(constants.BG_IMG_PATH, bg_id + ".jpg"))
    img_width = img.shape[1]
    img_height = img.shape[0]
    index = useful_space_data[useful_space_data["DataRow ID"] == bg_id].index[0]

    top = json.loads(useful_space_data.loc[index, "Label"])["objects"][0]["bbox"]["top"]
    left = json.loads(useful_space_data.loc[index, "Label"])["objects"][0]["bbox"]["left"]
    height = json.loads(useful_space_data.loc[index, "Label"])["objects"][0]["bbox"]["height"]
    width = json.loads(useful_space_data.loc[index, "Label"])["objects"][0]["bbox"]["width"]
    x1 = left / img_width,
    x2 = (left + width) / img_width,
    y1 = top / img_height,
    y2 = (top + height) / img_height
    return x1[0], x2[0], y1[0], y2


def download_bk_img(data_path=constants.LABEL_BOX_DATASET_PATH, save_path=constants.BG_IMG_PATH,
                    empty_labeled_num=1):
    downloaded_error_timeout_num = 0
    data_df = pd.read_csv(data_path)
    for i in np.arange(data_df.shape[0]):
        if data_df["Label"][i] == "{}":
            empty_labeled_num += 1
            continue
        else:
            url = data_df["Labeled Data"][i]
            id = data_df["DataRow ID"][i]
            img_name = id + ".jpg"
            if os.path.exists(os.path.join(save_path, img_name)):
                print("{}_downloaded exists".format(img_name))
                continue
            else:
                r = requests.get(url, timeout=10)
                f = BytesIO(r.content)
                img = Image.open(f)
                img = img.convert('RGB')
                path = os.path.join(save_path, img_name)
                img.save(path)
                print("{} downloaded".format(img_name))
    print("downloaded_error_timeout_num:{}".format(downloaded_error_timeout_num))
    print("empty_labeled_num:{}".format(empty_labeled_num))


def data_process(data_path=constants.PALETTES_DATA_PATH):
    '''

    :param data_path: 输入原始数据，
    :return: colour_hsv：hsv，colour_saves：喜爱度，colour_rgb：rgb的数据，
    以上均为pandas数据
    '''

    data = pd.read_csv(data_path, header=None)
    data.columns = ["1", "2", "3", "4", "5", "6", "7", "8", "saves"]
    data.drop([0], axis=0, inplace=True)
    data.fillna(axis=0, method='ffill', inplace=True)
    data.dropna(axis=0, inplace=True)
    colour_16th = data.iloc[:, :7]

    colour_rgb = colour_16th.copy()
    colour_hsv = colour_16th.copy()
    colour_saves = data.iloc[:, 8].map(lambda x: int(x.strip("saves").strip(" ").replace(",", "")))

    for _ in range(colour_hsv.shape[0]):
        colour_hsv.iloc[_, :] = colour_hsv.iloc[_, :].apply(functions_utils.hex_to_hsv)
    for _ in range(colour_rgb.shape[0]):
        colour_rgb.iloc[_, :] = colour_rgb.iloc[_, :].apply(functions_utils.hex_to_rgb)

    return colour_hsv, colour_saves, colour_rgb


def calculate(colour_hsv, main_colour_list, colour_rgb):
    '''
    取背景图的颜色，取n个，for循环，每个都算出一个distance。吧distance的结果放在result中，
    包括index（在每个色板的位置）和值
    :param colour_hsv: hsv
    :param main_colour_list: rgb格式的颜色，元祖list
    :return:
    '''
    # np.array:shape:(data.shape[0],num*2),最小值的索引，最小值
    result = pd.DataFrame(np.zeros((colour_hsv.shape[0], constants.MAP_NUM * 2)))

    for color_index, bk_color in enumerate(main_colour_list):
        bk_color = functions_utils.rgb2hsv(bk_color)
        colour_distance = colour_hsv.copy()
        # 计算distance的pandas
        for _ in range(colour_hsv.shape[0]):
            colour_distance.iloc[_, :] = colour_hsv.iloc[_, :].apply(
                lambda x: functions_utils.HSVDistance(x, bk_color))

        for _ in range(colour_distance.shape[0]):
            value_min = colour_distance.iloc[_, :].sort_values()[0]
            index_min = colour_distance.iloc[_, :][colour_distance.iloc[_, :] == value_min].index.values[0]
            result.iloc[_, color_index * 2] = index_min
            result.iloc[_, color_index * 2 + 1] = value_min

    result_min_index = (result.iloc[:, 1] + result.iloc[:, 3]).argmin()
    palettes = colour_rgb.iloc[result_min_index, :]
    mapped_color = set(result.iloc[result_min_index, [0, 2]])

    return palettes.tolist(), list(mapped_color)


def write_bg_color_palettes(bk_img_path=constants.BG_IMG_PATH):
    bk_img_list = os.listdir(bk_img_path)
    colour_hsv, colour_saves, colour_rgb = data_process(data_path=constants.PALETTES_DATA_PATH)
    container = {}
    try:
        bk_img_list.remove(".DS_Store")
    except:
        print("no .DS_Store")

    for _ in bk_img_list:
        bg_id = _[:-4]
        img_path = os.path.join(bk_img_path, _)
        main_colour_list = functions_utils.get_colour_cluster_list(img_path)
        bk_info_dic = {}

        # 写入字典
        palettes, mapped_color = calculate(colour_hsv, main_colour_list, colour_rgb)
        bk_info_dic["palettes"] = palettes
        bk_info_dic["mapped"] = mapped_color
        bk_info_dic["useful_space"] = get_useful_space_info(bg_id)

        container[bg_id] = bk_info_dic
        print("{}_done".format(bg_id))

    with open(constants.BG_IMG_INFO_PATH, "w") as e:
        json.dump(container, e, indent=4)


def add_one_color_theory_palettes():
    '''
    只降低明度和饱和度
    :return:
    '''
    main_color_data = json.load(open(constants.CACHE_PATH, "r"))
    bk_img_list = os.listdir(constants.BG_IMG_PATH)
    palettes_data = json.load(open(constants.BG_IMG_INFO_PATH, "r"))
    for _ in bk_img_list:
        main_color = main_color_data["./bg_img/" + _][0]
        id_ = _[:-4]
        h = main_color[0]
        s = main_color[1] * 0.618
        v = main_color[2] * 0.618

        r, g, b = functions_utils.hsv2rgb(h, s, v)
        palettes_data[id_]["one_color_theory"] = [r, g, b]
    json.dump(palettes_data, open(constants.BG_IMG_INFO_PATH, "w"), indent=4)


def add_adjacent_color_theory_palettes():
    '''
    30度之内的颜色
    :return:
    '''
    main_color_data = json.load(open(constants.CACHE_PATH, "r"))
    bk_img_list = os.listdir(constants.BG_IMG_PATH)
    palettes_data = json.load(open(constants.BG_IMG_INFO_PATH, "r"))
    for _ in bk_img_list:
        main_color = main_color_data["./bg_img/" + _][0]
        id_ = _[:-4]
        h = main_color[0] + 30
        if h > 360:
            h = h - 360
        s = main_color[1]
        v = main_color[2]

        r, g, b = functions_utils.hsv2rgb(h, s, v)
        palettes_data[id_]["adjacent_color_theory"] = [r, g, b]
    json.dump(palettes_data, open(constants.BG_IMG_INFO_PATH, "w"), indent=4)


def add_contrast_color_theory_palettes():
    '''
    30度之内的颜色
    :return:
    '''
    main_color_data = json.load(open(constants.CACHE_PATH, "r"))
    bk_img_list = os.listdir(constants.BG_IMG_PATH)
    palettes_data = json.load(open(constants.BG_IMG_INFO_PATH, "r"))
    for _ in bk_img_list:
        main_color = main_color_data["./bg_img/" + _][0]
        id_ = _[:-4]
        h = main_color[0] + 120
        if h > 360:
            h = h - 360
        s = main_color[1]
        v = main_color[2]

        r, g, b = functions_utils.hsv2rgb(h, s, v)
        palettes_data[id_]["contrast_color_theory"] = [r, g, b]
    json.dump(palettes_data, open(constants.BG_IMG_INFO_PATH, "w"), indent=4)


def pipeline():
    download_bk_img()
    write_bg_color_palettes()
    add_one_color_theory_palettes()


if __name__ == "__main__":
    '''
    step one:generate palettes with format with hsv
    step two:get posters main generate_background_info clusters
    param:n the num of colors that map
    step three:calculate n times ,get the list of min distance of each palettes ,add all
    chose the min 
    '''
    # download_bk_img()
    # write_bg_color_palettes()
    # add_one_color_theory_palettes()
    # add_adjacent_color_theory_palettes()
    add_contrast_color_theory_palettes()
