#include <opencv2/opencv.hpp>
#include <chrono>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    int port = 5000;
    if (argc > 1) port = std::stoi(argv[1]);

    std::string pipeline =
        "udpsrc port=" + std::to_string(port) + " buffer-size=4194304 "
        "caps=\"application/x-rtp,media=video,clock-rate=90000,encoding-name=JPEG,payload=26\" ! "
        "queue leaky=downstream max-size-buffers=2 ! "
        "rtpjpegdepay ! jpegdec ! videoconvert ! video/x-raw,format=BGR ! "
        "appsink drop=true sync=false max-buffers=1";

    std::cout << "Opening pipeline:\n" << pipeline << std::endl;
    cv::VideoCapture cap(pipeline, cv::CAP_GSTREAMER);
    if (!cap.isOpened()) {
        std::cerr << "Failed to open stream" << std::endl;
        return 1;
    }

    cv::Mat frame;
    std::size_t frames = 0;
    auto t0 = std::chrono::steady_clock::now();
    auto last = t0;

    while (true) {
        if (!cap.read(frame) || frame.empty()) {
            std::cerr << "No frame" << std::endl;
            continue;
        }
        ++frames;
        auto now = std::chrono::steady_clock::now();
        double dt = std::chrono::duration<double>(now - last).count();
        if (dt >= 2.0) {
            double total = std::chrono::duration<double>(now - t0).count();
            std::cout << "FPS=" << frames / total
                      << " frame=" << frame.cols << "x" << frame.rows << std::endl;
            last = now;
        }
    }
}
