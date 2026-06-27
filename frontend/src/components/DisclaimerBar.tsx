import { Alert } from 'antd';

const DisclaimerBar = () => (
  <Alert
    className="disclaimer"
    banner
    type="warning"
    message="本工具仅基于公开数据做AI量化统计，不构成任何投资建议；A股存在高波动风险，所有盈亏由用户自行承担。"
  />
);

export default DisclaimerBar;
