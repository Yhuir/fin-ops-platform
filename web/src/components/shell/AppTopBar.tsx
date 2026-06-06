import { Button, Tooltip } from "@heroui/react";
import { Menu } from "lucide-react";

type AppTopBarProps = {
  embedded: boolean;
  isCompact: boolean;
  onOpenMobileSidebar: () => void;
};

export default function AppTopBar({
  embedded,
  isCompact,
  onOpenMobileSidebar,
}: AppTopBarProps) {
  if (!isCompact) {
    return null;
  }

  return (
    <header className={`global-header${embedded ? " embedded-header" : ""}`}>
      <div className="global-toolbar">
        <div className="global-header-main">
          <Tooltip delay={250}>
            <Tooltip.Trigger>
              <Button
                isIconOnly
                aria-label="打开菜单"
                className="global-menu-button"
                size="sm"
                variant="tertiary"
                onPress={onOpenMobileSidebar}
              >
                <Menu aria-hidden="true" size={20} strokeWidth={2.1} />
              </Button>
            </Tooltip.Trigger>
            <Tooltip.Content placement="bottom" showArrow>
              <Tooltip.Arrow />
              打开菜单
            </Tooltip.Content>
          </Tooltip>
        </div>

        <div className="header-actions" />
      </div>
    </header>
  );
}
